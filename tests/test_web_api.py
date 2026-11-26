import asyncio
import io
import json
import uuid
import zipfile
from typing import Dict, List, Tuple

from web_api import app


def _encode_multipart(files: List[Tuple[str, str, bytes]], paths: List[str] = None) -> Tuple[bytes, str]:
    boundary = f"----GrafeandoTestBoundary{uuid.uuid4().hex}"
    chunks: List[bytes] = []

    for field_name, filename, content in files:
        chunks.append(f"--{boundary}\r\n".encode("utf-8"))
        chunks.append(
            f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'
            f"Content-Type: application/octet-stream\r\n\r\n".encode("utf-8")
        )
        chunks.append(content)
        chunks.append(b"\r\n")

    for path_val in (paths or []):
        chunks.append(f"--{boundary}\r\n".encode("utf-8"))
        chunks.append(
            f'Content-Disposition: form-data; name="paths"\r\n\r\n{path_val}\r\n'.encode("utf-8")
        )

    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
    body = b"".join(chunks)
    content_type = f"multipart/form-data; boundary={boundary}"
    return body, content_type


def _asgi_request(method: str, path: str, body: bytes = b"", headers: Dict[str, str] = None) -> Tuple[int, dict]:
    raw_headers = [(k.lower().encode("latin-1"), v.encode("latin-1")) for k, v in (headers or {}).items()]

    async def _run():
        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": method,
            "scheme": "http",
            "path": path,
            "raw_path": path.encode("ascii"),
            "query_string": b"",
            "headers": raw_headers,
            "client": ("127.0.0.1", 50000),
            "server": ("testserver", 80),
        }
        sent = False
        status_code = 500
        resp_chunks: List[bytes] = []

        async def receive():
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": body, "more_body": False}
            return {"type": "http.disconnect"}

        async def send(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            elif message["type"] == "http.response.body":
                resp_chunks.append(message.get("body", b""))

        await app(scope, receive, send)
        raw = b"".join(resp_chunks)
        return status_code, json.loads(raw.decode("utf-8"))

    return asyncio.run(_run())


def test_health_and_supported_endpoints():
    status, data = _asgi_request("GET", "/api/health")
    assert status == 200
    assert data["status"] == "ok"
    assert ".py" in data["supported_extensions"]
    assert ".tsx" in data["supported_extensions"]
    assert ".pdf" in data["supported_extensions"]

    status_sup, sup_data = _asgi_request("GET", "/api/supported")
    assert status_sup == 200
    assert len(sup_data["extensions"]) == 14
    assert "node_modules" in sup_data["ignored_dirs"]


def test_upload_folder_filters_files_and_builds_connected_graph():
    py_code = b"def helper():\n    return 1\n\ndef handler():\n    return helper()\n"
    tsx_code = (
        b"export function ChildBadge() { return <span>Hi</span>; }\n"
        b"export function ParentCard() { return <div><ChildBadge /></div>; }\n"
    )
    csv_code = b"id,user_id,total\n1,10,99.5\n"
    ignored_js = b"export function ShouldNotAppear() { return 0; }\n"
    binary_png = b"\x89PNG\r\n\x1a\n"

    paths = [
        "demo-app/src/api.py",
        "demo-app/src/App.tsx",
        "demo-app/data/orders.csv",
        "demo-app/node_modules/pkg/index.js",
        "demo-app/assets/logo.png",
    ]
    files = [
        ("files", "api.py", py_code),
        ("files", "App.tsx", tsx_code),
        ("files", "orders.csv", csv_code),
        ("files", "index.js", ignored_js),
        ("files", "logo.png", binary_png),
    ]
    body, content_type = _encode_multipart(files, paths=paths)
    status, data = _asgi_request(
        "POST",
        "/api/graph",
        body=body,
        headers={"content-type": content_type, "content-length": str(len(body))},
    )

    assert status == 200
    assert data["project_name"] == "demo-app"
    assert data["stats"]["files"] == 3
    assert data["stats"]["skipped_ignored"] == 1
    assert data["stats"]["skipped_unsupported"] == 1

    labels = {n["label"] for n in data["nodes"]}
    assert {"helper", "handler", "ChildBadge", "ParentCard", "orders.csv", "user_id"}.issubset(labels)
    assert "ShouldNotAppear" not in labels

    # Ensure paths were normalized relative to the uploaded folder (not /tmp/...)
    for node in data["nodes"]:
        assert not node["file_path"].startswith("/")
        assert "grafeando_upload_" not in node["file_path"]

    edge_types = {e["type"] for e in data["edges"]}
    assert "CALLS" in edge_types
    assert "RENDERS" in edge_types
    assert "CONTAINS" in edge_types


def test_upload_zip_archive_and_reject_unsupported_only():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("my-sql-proj/schema.sql", "CREATE TABLE users (id INT PRIMARY KEY);\nSELECT * FROM users;\n")
        zf.writestr("my-sql-proj/node_modules/skip.js", "function ignoredFn() {}")
        zf.writestr("../evil.py", "def traversal(): pass\n")

    body, content_type = _encode_multipart([("files", "my-sql-proj.zip", buf.getvalue())])
    status, data = _asgi_request(
        "POST",
        "/api/graph",
        body=body,
        headers={"content-type": content_type, "content-length": str(len(body))},
    )
    assert status == 200
    assert data["project_name"] == "my-sql-proj"
    labels = {n["label"] for n in data["nodes"]}
    assert "users" in labels
    assert "ignoredFn" not in labels

    # Unsupported-only upload returns HTTP 400 with clear guidance
    bad_body, bad_ct = _encode_multipart([("files", "image.png", b"not-code")])
    bad_status, bad_data = _asgi_request(
        "POST",
        "/api/graph",
        body=bad_body,
        headers={"content-type": bad_ct, "content-length": str(len(bad_body))},
    )
    assert bad_status == 400
    assert "Supported extensions" in bad_data["error"]
