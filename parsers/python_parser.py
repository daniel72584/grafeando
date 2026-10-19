from typing import List, Dict, Any, Optional
import tree_sitter_python as tspython
from tree_sitter import Language, Node
from parsers.tree_sitter_base import TreeSitterBaseParser, TraversalContext


class PythonParser(TreeSitterBaseParser):
    """
    Python AST parser using Strategy pattern for node dispatch.
    Extracts classes, functions, methods, FastAPI endpoints/Depends, calls, and imports.
    """

    def __init__(self):
        super().__init__(
            language=Language(tspython.language()),
            default_language_label="python"
        )
        self._register_strategies()

    def _register_strategies(self) -> None:
        self.register_handler(("import_statement", "import_from_statement"), self._handle_import)
        self.register_handler("class_definition", self._handle_class)
        self.register_handler(("function_definition", "async_function_definition"), self._handle_function)
        self.register_handler("decorated_definition", self._handle_decorated_definition)
        self.register_handler("call", self._handle_call)

    def _handle_import(self, node: Node, ctx: TraversalContext) -> None:
        imp_text = ctx.get_node_text(node).strip()
        ctx.res["imports"].append({"file_path": ctx.rel_path, "imported_module": imp_text})

    def _handle_class(self, node: Node, ctx: TraversalContext) -> None:
        name_node = node.child_by_field_name("name")
        if name_node:
            class_name = ctx.get_node_text(name_node)
            class_id = f"{ctx.rel_path}::{class_name}"
            ctx.res["classes"].append({
                "id": class_id,
                "name": class_name,
                "file_path": ctx.rel_path,
                "category": "class"
            })
            body_node = node.child_by_field_name("body")
            ctx.class_stack.append(class_name)
            self.traverse(body_node or node, ctx)
            ctx.class_stack.pop()
        else:
            self.traverse_children(node, ctx)

    def _handle_function(self, node: Node, ctx: TraversalContext) -> None:
        self._process_function_node(node, ctx, is_endpoint=False, decorators=[])

    def _handle_decorated_definition(self, node: Node, ctx: TraversalContext) -> None:
        definition_child = node.child_by_field_name("definition")
        decorators: List[str] = []
        is_fastapi_endpoint = False

        for c in node.children:
            if c.type == "decorator":
                dec_str = ctx.get_node_text(c).strip("@ ")
                decorators.append(dec_str)
                if any(dec_str.startswith(prefix) for prefix in (
                    "app.get", "app.post", "app.put", "app.delete", "app.patch",
                    "router.get", "router.post", "router.put", "router.delete", "router.patch"
                )):
                    is_fastapi_endpoint = True

        if definition_child and definition_child.type in ("function_definition", "async_function_definition"):
            self._process_function_node(definition_child, ctx, is_endpoint=is_fastapi_endpoint, decorators=decorators)
        else:
            self.traverse_children(node, ctx)

    def _process_function_node(
        self,
        node: Node,
        ctx: TraversalContext,
        is_endpoint: bool = False,
        decorators: Optional[List[str]] = None
    ) -> None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            self.traverse_children(node, ctx)
            return

        func_name = ctx.get_node_text(name_node)
        qualified_name = f"{ctx.class_stack[-1]}.{func_name}" if ctx.class_stack else func_name
        func_id = f"{ctx.rel_path}::{qualified_name}"
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1

        if is_endpoint:
            category = "endpoint"
        elif ctx.class_stack:
            category = "method"
        else:
            category = "function"

        func_info = {
            "id": func_id,
            "name": func_name,
            "qualified_name": qualified_name,
            "file_path": ctx.rel_path,
            "start_line": start_line,
            "end_line": end_line,
            "category": category
        }
        ctx.res["functions"].append(func_info)

        if ctx.class_stack:
            parent_class_id = f"{ctx.rel_path}::{ctx.class_stack[-1]}"
            ctx.res["contains"].append({
                "class_id": parent_class_id,
                "function_id": func_id
            })

        if decorators:
            for dec in decorators:
                ctx.res["decorators"].append({
                    "id": f"{func_id}@{dec}",
                    "name": dec,
                    "target_id": func_id,
                    "file_path": ctx.rel_path
                })

        params_node = node.child_by_field_name("parameters")
        if params_node:
            for p in params_node.children:
                if p.type in ("default_parameter", "typed_default_parameter"):
                    self._extract_fastapi_depends(p, func_info, ctx)

        body_node = node.child_by_field_name("body")
        ctx.func_stack.append(func_info)
        self.traverse(body_node or node, ctx)
        ctx.func_stack.pop()

    def _handle_call(self, node: Node, ctx: TraversalContext) -> None:
        if ctx.func_stack:
            caller_func = ctx.func_stack[-1]
            func_node = node.child_by_field_name("function")
            if func_node:
                callee_name = self._get_callee_name(func_node, ctx)
                if callee_name:
                    ctx.res["calls"].append({
                        "caller_id": caller_func["id"],
                        "callee_name": callee_name
                    })
        self.traverse_children(node, ctx)

    def _get_callee_name(self, func_node: Node, ctx: TraversalContext) -> Optional[str]:
        if func_node.type == "identifier":
            return ctx.get_node_text(func_node)
        elif func_node.type == "attribute":
            attribute_child = func_node.child_by_field_name("attribute")
            if attribute_child:
                return ctx.get_node_text(attribute_child)
            return ctx.get_node_text(func_node)
        return None

    def _extract_fastapi_depends(self, param_node: Node, func_info: Dict[str, Any], ctx: TraversalContext) -> None:
        for child in param_node.children:
            if child.type == "call":
                func_child = child.child_by_field_name("function")
                if func_child and ctx.get_node_text(func_child) == "Depends":
                    args_child = child.child_by_field_name("arguments")
                    if args_child:
                        for arg in args_child.children:
                            if arg.type in ("identifier", "attribute"):
                                dep_name = ctx.get_node_text(arg)
                                ctx.res["injects"].append({
                                    "injector_id": func_info["id"],
                                    "target_class_name": dep_name
                                })
                                ctx.res["calls"].append({
                                    "caller_id": func_info["id"],
                                    "callee_name": dep_name
                                })
