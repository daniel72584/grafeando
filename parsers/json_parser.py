import os
import json
from typing import Dict, List, Any
from parsers.base import BaseParser


class JsonParser(BaseParser):
    def parse_file(self, file_path: str, code_bytes: bytes) -> Dict[str, List[Dict[str, Any]]]:
        res = self.empty_result()
        rel_path = os.path.relpath(file_path)
        res["files"].append({"id": rel_path, "path": rel_path, "language": "json"})

        try:
            content_str = code_bytes.decode("utf-8", errors="replace")
            data = json.loads(content_str)
        except Exception as e:
            print(f"Error parsing JSON file {file_path}: {e}")
            return res

        filename = os.path.basename(file_path).lower()

        # 1. Package.json handling
        if filename == "package.json" and isinstance(data, dict):
            pkg_name = data.get("name", "app")
            res["classes"].append({
                "id": f"{rel_path}::{pkg_name}",
                "name": pkg_name,
                "file_path": rel_path,
                "category": "package"
            })

            deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
            for dep_name, dep_ver in deps.items():
                dep_id = f"npm::{dep_name}"
                res["classes"].append({
                    "id": dep_id,
                    "name": dep_name,
                    "file_path": rel_path,
                    "category": "npm_dependency"
                })
                res["imports"].append({
                    "file_path": rel_path,
                    "imported_module": f"{dep_name}@{dep_ver}"
                })
                res["injects"].append({
                    "injector_id": f"{rel_path}::{pkg_name}",
                    "target_class_name": dep_name
                })

        # 2. OpenAPI / Swagger spec handling
        elif isinstance(data, dict) and ("openapi" in data or "swagger" in data or "paths" in data):
            paths = data.get("paths", {})
            if isinstance(paths, dict):
                for path_url, path_item in paths.items():
                    if isinstance(path_item, dict):
                        for method, op in path_item.items():
                            if method.lower() in ("get", "post", "put", "delete", "patch", "options", "head") and isinstance(op, dict):
                                op_id = op.get("operationId") or f"{method.upper()}_{path_url.replace('/', '_')}"
                                endpoint_id = f"{rel_path}::{method.upper()} {path_url}"
                                res["functions"].append({
                                    "id": endpoint_id,
                                    "name": op_id,
                                    "qualified_name": f"{method.upper()} {path_url}",
                                    "file_path": rel_path,
                                    "start_line": 1,
                                    "end_line": 1,
                                    "category": "endpoint"
                                })

        # 3. Generic JSON handling
        elif isinstance(data, dict):
            for key in list(data.keys())[:20]:  # Limit top keys
                res["classes"].append({
                    "id": f"{rel_path}::{key}",
                    "name": str(key),
                    "file_path": rel_path,
                    "category": "config_key"
                })

        return res
