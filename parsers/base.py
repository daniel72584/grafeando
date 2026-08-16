from abc import ABC, abstractmethod
from typing import Dict, List, Any


class BaseParser(ABC):
    @abstractmethod
    def parse_file(self, file_path: str, code_bytes: bytes) -> Dict[str, List[Dict[str, Any]]]:
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
