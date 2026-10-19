from typing import List
import tree_sitter_java as tsjava
from tree_sitter import Language, Node
from parsers.tree_sitter_base import TreeSitterBaseParser, TraversalContext


class JavaParser(TreeSitterBaseParser):
    """
    Java AST parser using Strategy pattern.
    Extracts Spring Boot controllers/services, @Autowired/@Inject field dependencies,
    interfaces, methods, mapping endpoints, calls, and imports.
    """

    def __init__(self):
        super().__init__(
            language=Language(tsjava.language()),
            default_language_label="java"
        )
        self._register_strategies()

    def _register_strategies(self) -> None:
        self.register_handler("import_declaration", self._handle_import)
        self.register_handler(("class_declaration", "interface_declaration"), self._handle_class)
        self.register_handler("method_declaration", self._handle_method)
        self.register_handler("method_invocation", self._handle_call)

    def _handle_import(self, node: Node, ctx: TraversalContext) -> None:
        imp_text = ctx.get_node_text(node).strip()
        ctx.res["imports"].append({"file_path": ctx.rel_path, "imported_module": imp_text})

    def _handle_class(self, node: Node, ctx: TraversalContext) -> None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            self.traverse_children(node, ctx)
            return

        class_name = ctx.get_node_text(name_node)
        class_id = f"{ctx.rel_path}::{class_name}"
        annotations = self._extract_annotations(node, ctx)

        category = "interface" if node.type == "interface_declaration" else "class"
        if "Service" in annotations or "Service" in class_name:
            category = "service"
        elif "RestController" in annotations or "Controller" in annotations:
            category = "controller"

        ctx.res["classes"].append({
            "id": class_id,
            "name": class_name,
            "file_path": ctx.rel_path,
            "category": category
        })

        for ann in annotations:
            ctx.res["decorators"].append({
                "id": f"{class_id}@{ann}",
                "name": ann,
                "target_id": class_id,
                "file_path": ctx.rel_path
            })

        # Extract interface implementations
        interfaces_node = node.child_by_field_name("interfaces")
        if interfaces_node:
            for iface_type in interfaces_node.children:
                if iface_type.type == "type_identifier":
                    iface_name = ctx.get_node_text(iface_type)
                    ctx.res["implements"].append({
                        "class_id": class_id,
                        "interface_name": iface_name
                    })

        body_node = node.child_by_field_name("body")
        if body_node:
            # Inspect fields for Spring @Autowired or @Inject dependencies
            for field in body_node.children:
                if field.type == "field_declaration":
                    field_anns = self._extract_annotations(field, ctx)
                    if "Autowired" in field_anns or "Inject" in field_anns:
                        type_node = field.child_by_field_name("type")
                        if type_node:
                            dep_type_name = ctx.get_node_text(type_node)
                            ctx.res["injects"].append({
                                "injector_id": class_id,
                                "target_class_name": dep_type_name
                            })

        ctx.class_stack.append(class_name)
        self.traverse(body_node or node, ctx)
        ctx.class_stack.pop()

    def _handle_method(self, node: Node, ctx: TraversalContext) -> None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            self.traverse_children(node, ctx)
            return

        func_name = ctx.get_node_text(name_node)
        qualified_name = f"{ctx.class_stack[-1]}.{func_name}" if ctx.class_stack else func_name
        func_id = f"{ctx.rel_path}::{qualified_name}"
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1
        annotations = self._extract_annotations(node, ctx)

        category = "endpoint" if any(a.endswith("Mapping") for a in annotations) else "method"

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

        for ann in annotations:
            ctx.res["decorators"].append({
                "id": f"{func_id}@{ann}",
                "name": ann,
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

    def _handle_call(self, node: Node, ctx: TraversalContext) -> None:
        if ctx.func_stack:
            caller_func = ctx.func_stack[-1]
            name_node = node.child_by_field_name("name")
            if name_node:
                callee_name = ctx.get_node_text(name_node)
                ctx.res["calls"].append({
                    "caller_id": caller_func["id"],
                    "callee_name": callee_name
                })
        self.traverse_children(node, ctx)

    def _extract_annotations(self, node: Node, ctx: TraversalContext) -> List[str]:
        annotations = []
        for child in node.children:
            if child.type in ("annotation", "marker_annotation"):
                name_child = child.child_by_field_name("name")
                if name_child:
                    annotations.append(ctx.get_node_text(name_child))
                else:
                    annotations.append(ctx.get_node_text(child).strip("@ "))
            elif child.type == "modifiers":
                for mod_child in child.children:
                    if mod_child.type in ("annotation", "marker_annotation"):
                        name_child = mod_child.child_by_field_name("name")
                        if name_child:
                            annotations.append(ctx.get_node_text(name_child))
                        else:
                            annotations.append(ctx.get_node_text(mod_child).strip("@ "))
        return list(set(annotations))
