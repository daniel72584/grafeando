import io
import json
import os
import sys
import time
import zipfile
import tempfile
from pathlib import Path
from typing import List, Tuple

_pkg_root = str(Path(__file__).parent.resolve())
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)


def _load_dotenv(env_path: Path) -> None:
    """Lightweight .env loader (os.environ takes precedence over .env)."""
    if not env_path.is_file():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, val)


_load_dotenv(Path(__file__).parent.resolve() / ".env")

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

try:
    from grafeando.parser import CodeParser, SUPPORTED_EXTENSIONS_META
    from grafeando.graph_engine import GraphEngine
except ImportError:
    from parser import CodeParser, SUPPORTED_EXTENSIONS_META
    from graph_engine import GraphEngine

MAX_FILES = int(os.environ.get("GRAFEANDO_MAX_FILES", "600"))
MAX_TOTAL_BYTES = int(os.environ.get("GRAFEANDO_MAX_BYTES", str(25 * 1024 * 1024)))

code_parser = CodeParser()
SYSTEM_IGNORED_PARTS = code_parser.ignored_dirs.union({"__MACOSX", ".DS_Store", ".idea", ".vscode"})


def _normalize_rel_path(raw_path: str) -> str:
    """Sanitizes user-supplied relative file paths and blocks path traversal."""
    cleaned = raw_path.replace("\\", "/").strip().lstrip("/")
    parts = [p for p in cleaned.split("/") if p and p not in (".", "..")]
    return "/".join(parts)


def _is_ignored_path(rel_path: str) -> bool:
    parts = rel_path.split("/")
    for part in parts[:-1]:
        if part in SYSTEM_IGNORED_PARTS or (part.startswith(".") and part != ".agents"):
            return True
    filename = parts[-1] if parts else ""
    if filename in (".DS_Store", "Thumbs.db") or filename.startswith("._"):
        return True
    return False


def _strip_single_top_folder(paths_and_bytes: List[Tuple[str, bytes]]) -> Tuple[str, List[Tuple[str, bytes]]]:
    """
    If all uploaded files share a single root folder (e.g. 'my-app/src/index.ts'),
    strips that outer prefix so graph file paths start cleanly at 'src/index.ts',
    and returns 'my-app' as the detected project name.
    """
    if not paths_and_bytes:
        return "Uploaded Project", paths_and_bytes

    first_segments = {p.split("/")[0] for p, _ in paths_and_bytes if "/" in p}
    all_have_slash = all("/" in p for p, _ in paths_and_bytes)

    if all_have_slash and len(first_segments) == 1:
        project_name = next(iter(first_segments))
        prefix = project_name + "/"
        stripped = [(p[len(prefix):], b) for p, b in paths_and_bytes if p[len(prefix):]]
        return project_name, stripped

    if len(paths_and_bytes) == 1:
        return os.path.basename(paths_and_bytes[0][0]), paths_and_bytes

    return "Uploaded Project", paths_and_bytes


async def health_endpoint(request: Request) -> JSONResponse:
    return JSONResponse({
        "status": "ok",
        "service": "grafeando-web-api",
        "version": "1.0.0",
        "supported_extensions": [item["ext"] for item in SUPPORTED_EXTENSIONS_META],
    })


async def supported_endpoint(request: Request) -> JSONResponse:
    return JSONResponse({
        "extensions": SUPPORTED_EXTENSIONS_META,
        "ignored_dirs": sorted(code_parser.ignored_dirs),
        "limits": {
            "max_files": MAX_FILES,
            "max_total_bytes": MAX_TOTAL_BYTES,
        },
    })


async def generate_graph_endpoint(request: Request) -> JSONResponse:
    t0 = time.perf_counter()

    try:
        form = await request.form(max_files=MAX_FILES + 50, max_fields=MAX_FILES * 2 + 50)
    except Exception as exc:
        return JSONResponse(
            {"error": f"Invalid upload payload or too many files (max {MAX_FILES} supported files): {exc}"},
            status_code=400,
        )

    uploaded_files = form.getlist("files")
    explicit_paths = [str(p) for p in form.getlist("paths")]

    if not uploaded_files:
        return JSONResponse(
            {"error": "No files received. Upload a supported file, folder, or .zip archive."},
            status_code=400,
        )

    accepted_files: List[Tuple[str, bytes]] = []
    skipped_unsupported = 0
    skipped_ignored = 0
    total_bytes = 0
    archive_name = ""

    for idx, item in enumerate(uploaded_files):
        if not hasattr(item, "read"):
            continue

        raw_name = explicit_paths[idx] if idx < len(explicit_paths) and explicit_paths[idx] else getattr(item, "filename", "")
        rel_path = _normalize_rel_path(raw_name or f"file_{idx}")
        if not rel_path:
            continue

        content = await item.read()
        total_bytes += len(content)
        if total_bytes > MAX_TOTAL_BYTES:
            max_mb = MAX_TOTAL_BYTES // (1024 * 1024)
            return JSONResponse(
                {"error": f"Upload exceeds the {max_mb} MB limit. Please upload a smaller folder or exclude large assets."},
                status_code=413,
            )

        # Expand .zip archives in memory safely
        if rel_path.lower().endswith(".zip"):
            archive_name = os.path.splitext(os.path.basename(rel_path))[0]
            try:
                with zipfile.ZipFile(io.BytesIO(content)) as zf:
                    for info in zf.infolist():
                        if info.is_dir():
                            continue
                        member_path = _normalize_rel_path(info.filename)
                        if not member_path:
                            continue
                        if _is_ignored_path(member_path):
                            skipped_ignored += 1
                            continue
                        if not code_parser.is_supported_file(member_path):
                            skipped_unsupported += 1
                            continue
                        if len(accepted_files) >= MAX_FILES:
                            break
                        total_bytes += info.file_size
                        if total_bytes > MAX_TOTAL_BYTES * 2:
                            return JSONResponse(
                                {"error": "Uncompressed .zip content exceeds maximum allowed size."},
                                status_code=413,
                            )
                        accepted_files.append((member_path, zf.read(info)))
            except zipfile.BadZipFile:
                return JSONResponse({"error": f"'{rel_path}' is not a valid .zip archive."}, status_code=400)
            continue

        if _is_ignored_path(rel_path):
            skipped_ignored += 1
            continue

        if not code_parser.is_supported_file(rel_path):
            skipped_unsupported += 1
            continue

        if len(accepted_files) < MAX_FILES:
            accepted_files.append((rel_path, content))

    if not accepted_files:
        supported_list = ", ".join(item["ext"] for item in SUPPORTED_EXTENSIONS_META)
        return JSONResponse(
            {
                "error": (
                    f"No supported source files found in upload "
                    f"(skipped {skipped_unsupported} unsupported and {skipped_ignored} ignored files). "
                    f"Supported extensions: {supported_list}"
                )
            },
            status_code=400,
        )

    detected_name, normalized_entries = _strip_single_top_folder(accepted_files)
    project_name = archive_name or detected_name

    # Write into an ephemeral temp directory, parse ASTs, build in-memory graph, and wipe immediately
    with tempfile.TemporaryDirectory(prefix="grafeando_upload_") as tmp_dir:
        tmp_root = Path(tmp_dir).resolve()
        for rel_path, file_bytes in normalized_entries:
            target = (tmp_root / rel_path).resolve()
            # Strict path-traversal guard
            if not str(target).startswith(str(tmp_root)):
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(file_bytes)

        parsed_data = code_parser.parse_directory(str(tmp_root), relative_to_root=True)
        engine = GraphEngine(":memory:")
        engine.ingest_parse_data(parsed_data)
        graph_data = engine.export_graph_data()

    elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
    stats = graph_data.get("stats", {})
    stats.update({
        "skipped_unsupported": skipped_unsupported,
        "skipped_ignored": skipped_ignored,
        "elapsed_ms": elapsed_ms,
    })

    return JSONResponse({
        "project_name": project_name,
        "nodes": graph_data["nodes"],
        "edges": graph_data["edges"],
        "stats": stats,
    })


async def config_js_endpoint(request: Request) -> Response:
    config = {
        "RENDER_API_URL": os.environ.get("GRAFEANDO_API_URL", "").strip().rstrip("/"),
        "GITHUB_REPO_URL": os.environ.get(
            "GRAFEANDO_GITHUB_REPO_URL", "https://github.com/daniel72584/grafeando"
        ).strip(),
    }
    js_body = f"window.GRAFEANDO_CONFIG = {json.dumps(config, indent=2)};\n"
    return Response(content=js_body, media_type="application/javascript")


cors_origins_env = os.environ.get("GRAFEANDO_CORS_ORIGINS", "*")
allowed_origins = [o.strip() for o in cors_origins_env.split(",") if o.strip()] or ["*"]

routes = [
    Route("/api/health", health_endpoint, methods=["GET"]),
    Route("/api/supported", supported_endpoint, methods=["GET"]),
    Route("/api/graph", generate_graph_endpoint, methods=["POST"]),
    Route("/config.js", config_js_endpoint, methods=["GET"]),
]

docs_dir = Path(__file__).parent.resolve() / "docs"
if docs_dir.exists():
    routes.append(Mount("/", app=StaticFiles(directory=str(docs_dir), html=True), name="docs"))

app = Starlette(
    routes=routes,
    middleware=[
        Middleware(
            CORSMiddleware,
            allow_origins=allowed_origins,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["*"],
        )
    ],
)
