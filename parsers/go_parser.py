from typing import Optional
import tree_sitter_go as tsgo
from tree_sitter import Language, Node
from parsers.tree_sitter_base import TreeSitterBaseParser, TraversalContext


class GoParser(TreeSitterBaseParser):
    """
    Go AST parser using Strategy pattern.
    Extracts structs, interfaces, methods, functions, calls, and imports.
    """

    def __init__(self):
        super().__init__(
            language=Language(tsgo.language()),
            default_language_label="go"
        )
        self._register_strategies()

    def _register_strategies(self) -> None:
        self.register_handler("import_declaration", self._handle_import)
        self.register_handler("type_declaration", self._handle_type)
        self.register_handler("method_declaration", self._handle_method)
        self.register_handler("function_declaration", self._handle_function)
        self.register_handler("call_expression", self._handle_call)

    def _handle_import(self, node: Node, ctx: TraversalContext) -> None:
        imp_text = ctx.get_node_text(node).strip()
        ctx.res["imports"].append({"file_path": ctx.rel_path, "imported_module": imp_text})

    def _handle_type(self, node: Node, ctx: TraversalContext) -> None:
        for spec in node.children:
            if spec.type == "type_spec":
                name_node = spec.child_by_field_name("name")
                type_node = spec.child_by_field_name("type")
                if name_node:
                    struct_name = ctx.get_node_text(name_node)
                    struct_id = f"{ctx.rel_path}::{struct_name}"
                    category = "interface" if (type_node and type_node.type == "interface_type") else "struct"
                    ctx.res["classes"].append({
                        "id": struct_id,
                        "name": struct_name,
                        "file_path": ctx.rel_path,
                        "category": category
                    })
        self.traverse_children(node, ctx)

    def _handle_method(self, node: Node, ctx: TraversalContext) -> None:
        name_node = node.child_by_field_name("name")
        receiver_node = node.child_by_field_name("receiver")
        if not name_node:
            self.traverse_children(node, ctx)
            return

        func_name = ctx.get_node_text(name_node)
        receiver_type = "unknown"
        if receiver_node:
            rec_text = ctx.get_node_text(receiver_node).strip("()")
            parts = rec_text.rsplit(" ", 1)
            receiver_type = parts[-1].lstrip("*")

        qualified_name = f"{receiver_type}.{func_name}" if receiver_type != "unknown" else func_name
        func_id = f"{ctx.rel_path}::{qualified_name}"
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1

        func_info = {
            "id": func_id,
            "name": func_name,
            "qualified_name": qualified_name,
            "file_path": ctx.rel_path,
            "start_line": start_line,
            "end_line": end_line,
            "category": "method"
        }
        ctx.res["functions"].append(func_info)

        if receiver_type != "unknown":
            parent_class_id = f"{ctx.rel_path}::{receiver_type}"
            ctx.res["contains"].append({
                "class_id": parent_class_id,
                "function_id": func_id
            })

        body_node = node.child_by_field_name("body")
        ctx.func_stack.append(func_info)
        self.traverse(body_node or node, ctx)
        ctx.func_stack.pop()

    def _handle_function(self, node: Node, ctx: TraversalContext) -> None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            self.traverse_children(node, ctx)
            return

        func_name = ctx.get_node_text(name_node)
        func_id = f"{ctx.rel_path}::{func_name}"
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1

        func_info = {
            "id": func_id,
            "name": func_name,
            "qualified_name": func_name,
            "file_path": ctx.rel_path,
            "start_line": start_line,
            "end_line": end_line,
            "category": "function"
        }
        ctx.res["functions"].append(func_info)

        body_node = node.child_by_field_name("body")
        ctx.func_stack.append(func_info)
        self.traverse(body_node or node, ctx)
        ctx.func_stack.pop()

    def _handle_call(self, node: Node, ctx: TraversalContext) -> None:
        if ctx.func_stack:
            caller_func = ctx.func_stack[-1]
            func_node = node.child_by_field_name("function")
            if func_node:
                callee_name = self._extract_callee_name(func_node, ctx)
                if callee_name:
                    ctx.res["calls"].append({
                        "caller_id": caller_func["id"],
                        "callee_name": callee_name
                    })
        self.traverse_children(node, ctx)

    def _extract_callee_name(self, func_node: Node, ctx: TraversalContext) -> Optional[str]:
        if func_node.type == "identifier":
            return ctx.get_node_text(func_node)
        elif func_node.type == "selector_expression":
            field_child = func_node.child_by_field_name("field")
            if field_child:
                return ctx.get_node_text(field_child)
            return ctx.get_node_text(func_node)
        return None
