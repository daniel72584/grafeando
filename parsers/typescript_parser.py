from typing import Dict, List, Any, Optional
import tree_sitter_typescript as tsts
from tree_sitter import Language, Parser, Node
from parsers.tree_sitter_base import TreeSitterBaseParser, TraversalContext


class TypeScriptParser(TreeSitterBaseParser):
    """
    TypeScript and TSX AST parser using Strategy pattern and Chain of Responsibility.
    Extracts NestJS controllers/services/modules, dependency injection constructor parameters,
    React components, hooks, JSX render trees, and calls.
    """

    def __init__(self):
        self.ts_language = Language(tsts.language_typescript())
        self.tsx_language = Language(tsts.language_tsx())
        self.tsx_parser = Parser(self.tsx_language)
        super().__init__(
            language=self.ts_language,
            default_language_label="typescript"
        )
        self._register_middlewares()
        self._register_strategies()

    def get_parser(self, file_path: str) -> Parser:
        if file_path.endswith((".tsx", ".jsx")):
            return self.tsx_parser
        return self.parser

    def get_language_label(self, file_path: str) -> str:
        if file_path.endswith((".tsx", ".jsx")):
            return "tsx"
        return "typescript"

    def _register_middlewares(self) -> None:
        self.register_middleware(self._decorator_middleware)

    def _register_strategies(self) -> None:
        self.register_handler("import_statement", self._handle_import)
        self.register_handler("export_statement", self._handle_export)
        self.register_handler("class_declaration", self._handle_class)
        self.register_handler(
            ("function_declaration", "method_definition", "arrow_function"),
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
        if not name_node:
            self.traverse_children(node, ctx)
            ctx.pending_decorators.clear()
            return

        class_name = ctx.get_node_text(name_node)
        class_id = f"{ctx.rel_path}::{class_name}"
        decorators = list(set(ctx.pending_decorators + self._extract_decorator_names(node.children, ctx)))
        ctx.pending_decorators.clear()

        category = "class"
        if "Controller" in decorators:
            category = "controller"
        elif "Injectable" in decorators or "Service" in class_name:
            category = "service"
        elif "Module" in decorators:
            category = "module"

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

        # Extract interfaces implemented
        for c in node.children:
            if c.type == "class_heritage":
                for h_child in c.children:
                    if h_child.type == "implements_clause":
                        for iface_node in h_child.children:
                            if iface_node.type in ("type_identifier", "generic_type"):
                                iface_name = ctx.get_node_text(iface_node).split("<")[0].strip()
                                if iface_name and iface_name != "implements":
                                    ctx.res["implements"].append({
                                        "class_id": class_id,
                                        "interface_name": iface_name
                                    })

        # Extract NestJS Constructor Dependency Injection
        body_node = node.child_by_field_name("body")
        if body_node:
            for m in body_node.children:
                if m.type == "method_definition":
                    m_name_node = m.child_by_field_name("name")
                    if m_name_node and ctx.get_node_text(m_name_node) == "constructor":
                        params_node = m.child_by_field_name("parameters")
                        if params_node:
                            def find_type_identifiers(p_node: Node) -> List[str]:
                                found = []
                                if p_node.type == "type_identifier":
                                    found.append(ctx.get_node_text(p_node))
                                for c_node in p_node.children:
                                    found.extend(find_type_identifiers(c_node))
                                return found

                            for param in params_node.children:
                                for target_dep_name in find_type_identifiers(param):
                                    if target_dep_name and target_dep_name != class_name:
                                        ctx.res["injects"].append({
                                            "injector_id": class_id,
                                            "target_class_name": target_dep_name
                                        })

        ctx.class_stack.append(class_name)
        self.traverse(body_node or node, ctx)
        ctx.class_stack.pop()

    def _handle_function(self, node: Node, ctx: TraversalContext) -> None:
        name_node = node.child_by_field_name("name")
        func_name = ctx.get_node_text(name_node) if name_node else None

        if not func_name and node.parent and node.parent.type == "variable_declarator":
            var_name_node = node.parent.child_by_field_name("name")
            if var_name_node:
                func_name = ctx.get_node_text(var_name_node)

        if not func_name:
            self.traverse_children(node, ctx)
            ctx.pending_decorators.clear()
            return

        is_tsx = ctx.file_path.endswith((".tsx", ".jsx"))
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
        elif func_name[0].isupper() or is_tsx:
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
