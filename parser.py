import os
from typing import Dict, List, Any
from parsers import (
    PythonParser, TypeScriptParser, GoParser, JavaParser,
    JsonParser, SqlParser, MarkdownParser, CsvParser, PdfParser
)


class CodeParser:
    def __init__(self):
        self.parsers = {
            ".py": PythonParser(),
            ".ts": TypeScriptParser(),
            ".tsx": TypeScriptParser(),
            ".js": TypeScriptParser(),
            ".jsx": TypeScriptParser(),
            ".go": GoParser(),
            ".java": JavaParser(),
            ".json": JsonParser(),
            ".sql": SqlParser(),
            ".md": MarkdownParser(),
            ".csv": CsvParser(),
            ".pdf": PdfParser()
        }
        self.ignored_dirs = {
            "venv", "env", "__pycache__", "build", "dist",
            "node_modules", ".next", "target", "vendor", ".git", ".agents", "real_test_repos"
        }

    def parse_file(self, file_path: str) -> Dict[str, List[Dict[str, Any]]]:
        ext = os.path.splitext(file_path)[1].lower()
        parser = self.parsers.get(ext)

        empty_res = {
            "files": [], "classes": [], "functions": [], "contains": [],
            "calls": [], "injects": [], "renders": [], "implements": [],
            "decorators": [], "imports": []
        }

        if not parser:
            return empty_res

        try:
            with open(file_path, "rb") as f:
                code_bytes = f.read()
            return parser.parse_file(file_path, code_bytes)
        except Exception as e:
            print(f"Error reading file {file_path}: {e}")
            return empty_res

    def find_project_root(self, path: str = ".") -> str:
        """Finds the true project root by looking upwards for markers (.git, package.json, go.mod, etc.)."""
        current = os.path.abspath(path)
        markers = {".git", "package.json", "go.mod", "pom.xml", "Cargo.toml", "pyproject.toml", "setup.py"}

        while current and current != os.path.dirname(current):
            if any(os.path.exists(os.path.join(current, marker)) for marker in markers):
                return current
            current = os.path.dirname(current)
        return os.path.abspath(path)

    def parse_directory(self, root_dir: str) -> Dict[str, List[Dict[str, Any]]]:
        combined_data: Dict[str, List[Dict[str, Any]]] = {
            "files": [],
            "classes": [],
            "functions": [],
            "contains": [],
            "calls": [],
            "injects": [],
            "renders": [],
            "implements": [],
            "decorators": [],
            "imports": []
        }

        abs_root = os.path.abspath(root_dir)

        # Parse .gitignore entries if present
        extra_ignores = set()
        gitignore_path = os.path.join(abs_root, ".gitignore")
        if os.path.exists(gitignore_path):
            try:
                with open(gitignore_path, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#"):
                            clean_entry = line.strip("/").rstrip("/*")
                            if clean_entry:
                                extra_ignores.add(clean_entry)
            except Exception:
                pass

        all_ignored = self.ignored_dirs.union(extra_ignores)

        for dirpath, dirnames, filenames in os.walk(abs_root):
            dirnames[:] = [
                d for d in dirnames
                if not d.startswith(".") and d not in all_ignored
            ]
            for f in filenames:
                ext = os.path.splitext(f)[1].lower()
                if ext in self.parsers:
                    full_path = os.path.join(dirpath, f)
                    res = self.parse_file(full_path)
                    for key in combined_data:
                        combined_data[key].extend(res.get(key, []))

        return combined_data
