from typing import Dict, List, Any, Optional
import tree_sitter_javascript as tsjs
from tree_sitter import Language, Node
from parsers.tree_sitter_base import TreeSitterBaseParser, TraversalContext


class JavaScriptParser(TreeSitterBaseParser):
    """
    JavaScript and JSX AST parser using Strategy pattern and Chain of Responsibility.
    Extracts React components, JSX render hierarchy, hooks, CommonJS/ES imports, classes, and calls.
    """

    def __init__(self):
        super().__init__(
            language=Language(tsjs.language()),
            default_language_label="javascript"
        )
        self._register_middlewares()
        self._register_strategies()

    def get_language_label(self, file_path: str) -> str:
        if file_path.endswith((".jsx", ".cjsx", ".mjsx")):
            return "jsx"
        return "javascript"

    def _register_middlewares(self) -> None:
        # Chain of Responsibility: collect decorators before reaching class/function handlers
        self.register_middleware(self._decorator_middleware)

    def _register_strategies(self) -> None:
        self.register_handler("import_statement", self._handle_import)
        self.register_handler("export_statement", self._handle_export)
        self.register_handler(("class_declaration", "class"), self._handle_class)
        self.register_handler(
            (
                "function_declaration",
                "generator_function_declaration",
                "method_definition",
                "arrow_function",
                "function_expression",
            ),
            self._handle_function,
        )
        self.register_handler(("jsx_element", "jsx_self_closing_element"), self._handle_jsx)
        self.register_handler("call_expression", self._handle_call)

    def _decorator_middleware(self, node: Node, ctx: TraversalContext) -> bool:
        if node.type == "decorator":
            dec_text = ctx.get_node_text(node).strip("@ ")
            dec_name = dec_text.split("(")[0].strip()
            ctx.pending_decorators.append(dec_name)
            return True
        return False

    def _handle_import(self, node: Node, ctx: TraversalContext) -> None:
        imp_text = ctx.get_node_text(node).strip()
        ctx.res["imports"].append({"file_path": ctx.rel_path, "imported_module": imp_text})
        ctx.pending_decorators.clear()

    def _handle_export(self, node: Node, ctx: TraversalContext) -> None:
        self.traverse_children(node, ctx)
        ctx.pending_decorators.clear()

    def _handle_class(self, node: Node, ctx: TraversalContext) -> None:
        name_node = node.child_by_field_name("name")
        class_name = ctx.get_node_text(name_node) if name_node else None

        if not class_name and node.parent and node.parent.type == "variable_declarator":
            var_name_node = node.parent.child_by_field_name("name")
            if var_name_node:
                class_name = ctx.get_node_text(var_name_node)

        if not class_name:
            self.traverse_children(node, ctx)
            ctx.pending_decorators.clear()
            return

        class_id = f"{ctx.rel_path}::{class_name}"
        decorators = list(set(ctx.pending_decorators + self._extract_decorator_names(node.children, ctx)))
        ctx.pending_decorators.clear()

        category = "class"
        if "Controller" in decorators or class_name.endswith("Controller"):
            category = "controller"
        elif "Injectable" in decorators or "Service" in class_name:
            category = "service"
        elif "Module" in decorators or class_name.endswith("Module"):
            category = "module"

        # Check inheritance / implements
        for c in node.children:
            if c.type == "class_heritage":
                for h_child in c.children:
                    if h_child.type in ("identifier", "member_expression"):
                        base_name = ctx.get_node_text(h_child)
                        if base_name and base_name != "extends":
                            ctx.res["implements"].append({
                                "class_id": class_id,
                                "interface_name": base_name
                            })
                            if base_name in ("Component", "PureComponent", "React.Component", "React.PureComponent"):
                                category = "component"
                    elif h_child.type in ("extends_clause", "extends"):
                        for sub_c in h_child.children:
                            if sub_c.type in ("identifier", "member_expression"):
                                base_name = ctx.get_node_text(sub_c)
                                if base_name and base_name != "extends":
                                    ctx.res["implements"].append({
                                        "class_id": class_id,
                                        "interface_name": base_name
                                    })
                                    if base_name in ("Component", "PureComponent", "React.Component", "React.PureComponent"):
                                        category = "component"
                    elif h_child.type == "implements_clause":
                        for iface_node in h_child.children:
                            if iface_node.type in ("type_identifier", "generic_type", "identifier"):
                                iface_name = ctx.get_node_text(iface_node).split("<")[0].strip()
                                if iface_name and iface_name != "implements":
                                    ctx.res["implements"].append({
                                        "class_id": class_id,
                                        "interface_name": iface_name
                                    })

        ctx.res["classes"].append({
            "id": class_id,
            "name": class_name,
            "file_path": ctx.rel_path,
            "category": category
        })

        for dec in decorators:
            ctx.res["decorators"].append({
                "id": f"{class_id}@{dec}",
                "name": dec,
                "target_id": class_id,
                "file_path": ctx.rel_path
            })

        body_node = node.child_by_field_name("body")
        ctx.class_stack.append(class_name)
        self.traverse(body_node or node, ctx)
        ctx.class_stack.pop()

    def _handle_function(self, node: Node, ctx: TraversalContext) -> None:
        func_name = self._extract_func_name(node, ctx)
        if not func_name:
            self.traverse_children(node, ctx)
            ctx.pending_decorators.clear()
            return

        is_jsx = ctx.file_path.endswith((".jsx", ".cjsx", ".mjsx"))
        qualified_name = f"{ctx.class_stack[-1]}.{func_name}" if ctx.class_stack else func_name
        func_id = f"{ctx.rel_path}::{qualified_name}"
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1
        decorators = list(set(ctx.pending_decorators + self._extract_decorator_names(node.children, ctx)))
        ctx.pending_decorators.clear()

        category = "function"
        if ctx.class_stack:
            category = "method"
        elif func_name.startswith("use") and len(func_name) > 3 and func_name[3].isupper():
            category = "hook"
        elif func_name[0].isupper() or is_jsx:
            category = "component"

        if any(d in ("Get", "Post", "Put", "Delete", "Patch") for d in decorators):
            category = "endpoint"

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

        for dec in decorators:
            ctx.res["decorators"].append({
                "id": f"{func_id}@{dec}",
                "name": dec,
                "target_id": func_id,
                "file_path": ctx.rel_path
            })

        if ctx.class_stack:
            parent_class_id = f"{ctx.rel_path}::{ctx.class_stack[-1]}"
            ctx.res["contains"].append({
                "class_id": parent_class_id,
                "function_id": func_id
            })

        body_node = node.child_by_field_name("body")
        ctx.func_stack.append(func_info)
        self.traverse(body_node or node, ctx)
        ctx.func_stack.pop()

    def _handle_jsx(self, node: Node, ctx: TraversalContext) -> None:
        rendered_comp = self._extract_jsx_tag_name(node, ctx)
        if rendered_comp and rendered_comp[0].isupper() and ctx.func_stack:
            caller_func = ctx.func_stack[-1]
            ctx.res["renders"].append({
                "parent_func_id": caller_func["id"],
                "rendered_component_name": rendered_comp
            })
        self.traverse_children(node, ctx)

    def _handle_call(self, node: Node, ctx: TraversalContext) -> None:
        func_node = node.child_by_field_name("function")
        callee_name = self._extract_callee_name(func_node, ctx) if func_node else None

        # CommonJS require('...') or dynamic import('...')
        if callee_name in ("require", "import"):
            args_node = node.child_by_field_name("arguments")
            if args_node and args_node.children:
                for arg in args_node.children:
                    if arg.type in ("string", "template_string"):
                        mod_name = ctx.get_node_text(arg).strip("'\"`")
                        ctx.res["imports"].append({
                            "file_path": ctx.rel_path,
                            "imported_module": mod_name
                        })
                        break

        if ctx.func_stack and callee_name:
            caller_func = ctx.func_stack[-1]
            ctx.res["calls"].append({
                "caller_id": caller_func["id"],
                "callee_name": callee_name
            })

        self.traverse_children(node, ctx)

    def _extract_callee_name(self, func_node: Node, ctx: TraversalContext) -> Optional[str]:
        if func_node.type == "identifier":
            return ctx.get_node_text(func_node)
        elif func_node.type == "member_expression":
            property_child = func_node.child_by_field_name("property")
            if property_child:
                return ctx.get_node_text(property_child)
            return ctx.get_node_text(func_node)
        return None

    def _extract_decorator_names(self, nodes: List[Node], ctx: TraversalContext) -> List[str]:
        decorators = []
        for n in nodes:
            if n.type == "decorator":
                dec_text = ctx.get_node_text(n).strip("@ ")
                dec_name = dec_text.split("(")[0].strip()
                decorators.append(dec_name)
        return decorators

    def _extract_jsx_tag_name(self, jsx_node: Node, ctx: TraversalContext) -> Optional[str]:
        if jsx_node.type == "jsx_element":
            for c in jsx_node.children:
                if c.type == "jsx_opening_element":
                    for gc in c.children:
                        if gc.type in ("identifier", "nested_identifier", "member_expression"):
                            return ctx.get_node_text(gc)
        elif jsx_node.type == "jsx_self_closing_element":
            for gc in jsx_node.children:
                if gc.type in ("identifier", "nested_identifier", "member_expression"):
                    return ctx.get_node_text(gc)
        return None

    def _extract_func_name(self, node: Node, ctx: TraversalContext) -> Optional[str]:
        name_node = node.child_by_field_name("name")
        if name_node:
            return ctx.get_node_text(name_node)

        parent = node.parent
        if not parent:
            return None

        if parent.type == "variable_declarator":
            var_name = parent.child_by_field_name("name")
            if var_name:
                return ctx.get_node_text(var_name)
        elif parent.type == "pair":
            key_node = parent.child_by_field_name("key")
            if key_node:
                return ctx.get_node_text(key_node)
        elif parent.type == "assignment_expression":
            left = parent.child_by_field_name("left")
            if left:
                if left.type == "member_expression":
                    prop = left.child_by_field_name("property")
                    if prop:
                        return ctx.get_node_text(prop)
                return ctx.get_node_text(left)
        elif parent.type == "arguments" and parent.parent and parent.parent.type == "call_expression":
            call_expr = parent.parent
            if call_expr.parent and call_expr.parent.type == "variable_declarator":
                var_name = call_expr.parent.child_by_field_name("name")
                if var_name:
                    return ctx.get_node_text(var_name)
            elif call_expr.parent and call_expr.parent.type == "assignment_expression":
                left = call_expr.parent.child_by_field_name("left")
                if left:
                    if left.type == "member_expression":
                        prop = left.child_by_field_name("property")
                        if prop:
                            return ctx.get_node_text(prop)
                    return ctx.get_node_text(left)
        return None
