import os
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional


class BaseParser(ABC):
    @abstractmethod
    def parse_file(
        self,
        file_path: str,
        code_bytes: bytes,
        base_dir: Optional[str] = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Parses raw code bytes for a file and returns extracted AST entities.
        Returns a dict with keys:
            - files
            - classes
            - functions
            - contains
            - calls
            - injects
            - renders
            - implements
            - decorators
            - imports
        """
        pass

    def get_rel_path(self, file_path: str, base_dir: Optional[str] = None) -> str:
        rel = os.path.relpath(file_path, base_dir) if base_dir else os.path.relpath(file_path)
        return rel.replace("\\", "/")

    def empty_result(self) -> Dict[str, List[Dict[str, Any]]]:
        return {
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
