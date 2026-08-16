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

        for dirpath, dirnames, filenames in os.walk(root_dir):
            dirnames[:] = [
                d for d in dirnames
                if not d.startswith(".") and d not in self.ignored_dirs
            ]
            for f in filenames:
                ext = os.path.splitext(f)[1].lower()
                if ext in self.parsers:
                    full_path = os.path.join(dirpath, f)
                    res = self.parse_file(full_path)
                    for key in combined_data:
                        combined_data[key].extend(res.get(key, []))

        return combined_data
