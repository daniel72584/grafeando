import os
from typing import Dict, List, Any, Optional
from parsers import (
    PythonParser, TypeScriptParser, JavaScriptParser, GoParser, JavaParser,
    JsonParser, SqlParser, MarkdownParser, CsvParser, PdfParser
)

SUPPORTED_EXTENSIONS_META = [
    {"ext": ".py", "language": "Python", "details": "Classes, functions, FastAPI endpoints & Depends"},
    {"ext": ".ts", "language": "TypeScript", "details": "NestJS controllers/services/DI, interfaces, calls"},
    {"ext": ".tsx", "language": "React TSX", "details": "Components, JSX render hierarchy, hooks"},
    {"ext": ".js", "language": "JavaScript", "details": "ES/CommonJS modules, classes, functions"},
    {"ext": ".jsx", "language": "React JSX", "details": "Components, JSX render trees, hooks"},
    {"ext": ".mjs", "language": "JavaScript (ESM)", "details": "ES modules, functions, calls"},
    {"ext": ".cjs", "language": "JavaScript (CJS)", "details": "CommonJS modules, functions, calls"},
    {"ext": ".go", "language": "Go", "details": "Structs, interfaces, receiver methods, calls"},
    {"ext": ".java", "language": "Java", "details": "Spring Boot controllers/services, @Autowired, interfaces"},
    {"ext": ".sql", "language": "SQL", "details": "CREATE TABLE, foreign keys, SELECT/DML queries"},
    {"ext": ".json", "language": "JSON", "details": "package.json dependencies, OpenAPI/Swagger endpoints, config"},
    {"ext": ".md", "language": "Markdown", "details": "Document sections, headings, internal file links"},
    {"ext": ".csv", "language": "CSV", "details": "Datasets, column schemas, *_id foreign key links"},
    {"ext": ".pdf", "language": "PDF", "details": "Document structure, pages, extracted URLs"},
]


class CodeParser:
    def __init__(self):
        self.parsers = {
            ".py": PythonParser(),
            ".ts": TypeScriptParser(),
            ".tsx": TypeScriptParser(),
            ".js": JavaScriptParser(),
            ".jsx": JavaScriptParser(),
            ".mjs": JavaScriptParser(),
            ".cjs": JavaScriptParser(),
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
            "node_modules", ".next", "target", "vendor", ".git", "real_test_repos",
            "graphify-out", "coverage"
        }

    def is_supported_file(self, file_path: str) -> bool:
        ext = os.path.splitext(file_path)[1].lower()
        return ext in self.parsers

    def parse_file(
        self,
        file_path: str,
        base_dir: Optional[str] = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
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
            return parser.parse_file(file_path, code_bytes, base_dir=base_dir)
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

    def parse_directory(
        self,
        root_dir: str,
        relative_to_root: bool = False,
    ) -> Dict[str, List[Dict[str, Any]]]:
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
        base_dir = abs_root if relative_to_root else None

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
                if (d == ".agents" or not d.startswith(".")) and d not in all_ignored
            ]
            for f in filenames:
                ext = os.path.splitext(f)[1].lower()
                if ext in self.parsers:
                    full_path = os.path.join(dirpath, f)
                    res = self.parse_file(full_path, base_dir=base_dir)
                    for key in combined_data:
                        combined_data[key].extend(res.get(key, []))

        return combined_data
