import os
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Callable, Union, Iterable
from tree_sitter import Language, Parser, Node
from parsers.base import BaseParser


@dataclass
class TraversalContext:
    file_path: str
    rel_path: str
    code_bytes: bytes
    res: Dict[str, List[Dict[str, Any]]]
    class_stack: List[str] = field(default_factory=list)
    func_stack: List[Dict[str, Any]] = field(default_factory=list)
    pending_decorators: List[str] = field(default_factory=list)

    def get_node_text(self, node: Node) -> str:
        return self.code_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


HandlerType = Callable[[Node, TraversalContext], None]
MiddlewareType = Callable[[Node, TraversalContext], bool]


class TreeSitterBaseParser(BaseParser):
    """
    Base class for Tree-Sitter AST parsers implementing:
      - Strategy Pattern: O(1) handler dispatch per AST node type.
      - Chain of Responsibility: Middleware pipeline for pre-processing nodes (e.g. decorators, exports).
    """

    def __init__(self, language: Language, default_language_label: str):
        self.language = language
        self.parser = Parser(self.language)
        self.default_language_label = default_language_label
        self._handlers: Dict[str, HandlerType] = {}
        self._middlewares: List[MiddlewareType] = []

    def register_handler(self, node_types: Union[str, Iterable[str]], handler: HandlerType) -> None:
        """Registers a Strategy handler for one or more AST node types."""
        if isinstance(node_types, str):
            node_types = [node_types]
        for nt in node_types:
            self._handlers[nt] = handler

    def register_middleware(self, middleware: MiddlewareType) -> None:
        """
        Registers a Chain of Responsibility middleware.
        If middleware(node, ctx) returns True, node processing stops for this node.
        """
        self._middlewares.append(middleware)

    def get_parser(self, file_path: str) -> Parser:
        """Hook to return custom Parser instance based on file type (e.g. TS vs TSX)."""
        return self.parser

    def get_language_label(self, file_path: str) -> str:
        return self.default_language_label

    def parse_file(self, file_path: str, code_bytes: bytes) -> Dict[str, List[Dict[str, Any]]]:
        res = self.empty_result()
        rel_path = os.path.relpath(file_path)
        lang_label = self.get_language_label(file_path)
        res["files"].append({"id": rel_path, "path": rel_path, "language": lang_label})

        parser = self.get_parser(file_path)
        try:
            tree = parser.parse(code_bytes)
        except Exception as e:
            print(f"Error parsing {lang_label} file {file_path}: {e}")
            return res

        ctx = TraversalContext(
            file_path=file_path,
            rel_path=rel_path,
            code_bytes=code_bytes,
            res=res,
        )

        self.traverse(tree.root_node, ctx)
        return res

    def traverse(self, node: Node, ctx: TraversalContext) -> None:
        """Executes Chain of Responsibility middlewares, then dispatches to Strategy handler."""
        # 1. Chain of Responsibility: pre-processing middlewares
        for middleware in self._middlewares:
            if middleware(node, ctx):
                return

        # 2. Strategy Pattern: O(1) node handler dispatch
        handler = self._handlers.get(node.type)
        if handler:
            handler(node, ctx)
        else:
            self.traverse_children(node, ctx)

    def traverse_children(self, node: Node, ctx: TraversalContext) -> None:
        """Default Strategy: recursively traverses all child nodes."""
        for child in node.children:
            self.traverse(child, ctx)
