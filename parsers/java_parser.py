import os
from typing import Dict, List, Any, Optional
import tree_sitter_java as tsjava
from tree_sitter import Language, Parser, Node
from parsers.base import BaseParser


class JavaParser(BaseParser):
    def __init__(self):
        self.language = Language(tsjava.language())
        self.parser = Parser(self.language)

    def parse_file(self, file_path: str, code_bytes: bytes) -> Dict[str, List[Dict[str, Any]]]:
        res = self.empty_result()
        rel_path = os.path.relpath(file_path)
        res["files"].append({"id": rel_path, "path": rel_path, "language": "java"})

        try:
            tree = self.parser.parse(code_bytes)
        except Exception as e:
            print(f"Error parsing Java file {file_path}: {e}")
            return res

        root_node = tree.root_node

        def get_node_text(node: Node) -> str:
            return code_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace")

        def extract_annotations(node: Node) -> List[str]:
            annotations = []
            for child in node.children:
                if child.type in ("annotation", "marker_annotation"):
                    name_child = child.child_by_field_name("name")
                    if name_child:
                        annotations.append(get_node_text(name_child))
                    else:
                        annotations.append(get_node_text(child).strip("@ "))
            # Check previous sibling modifiers if present
            for child in node.children:
                if child.type == "modifiers":
                    for mod_child in child.children:
                        if mod_child.type in ("annotation", "marker_annotation"):
                            name_child = mod_child.child_by_field_name("name")
                            if name_child:
                                annotations.append(get_node_text(name_child))
                            else:
                                annotations.append(get_node_text(mod_child).strip("@ "))
            return list(set(annotations))

        def traverse(node: Node, class_stack: List[str], func_stack: List[Dict[str, Any]]):
            for child in node.children:
                if child.type == "import_declaration":
                    imp_text = get_node_text(child).strip()
                    res["imports"].append({"file_path": rel_path, "imported_module": imp_text})

                elif child.type in ("class_declaration", "interface_declaration"):
                    name_node = child.child_by_field_name("name")
                    if name_node:
                        class_name = get_node_text(name_node)
                        class_id = f"{rel_path}::{class_name}"
                        annotations = extract_annotations(child)

                        category = "interface" if child.type == "interface_declaration" else "class"
                        if "Service" in annotations or "Service" in class_name:
                            category = "service"
                        elif "RestController" in annotations or "Controller" in annotations:
                            category = "controller"

                        res["classes"].append({
                            "id": class_id,
                            "name": class_name,
                            "file_path": rel_path,
                            "category": category
                        })

                        for ann in annotations:
                            res["decorators"].append({
                                "id": f"{class_id}@{ann}",
                                "name": ann,
                                "target_id": class_id,
                                "file_path": rel_path
                            })

                        # Extract interface implementations
                        interfaces_node = child.child_by_field_name("interfaces")
                        if interfaces_node:
                            for iface_type in interfaces_node.children:
                                if iface_type.type == "type_identifier":
                                    iface_name = get_node_text(iface_type)
                                    res["implements"].append({
                                        "class_id": class_id,
                                        "interface_name": iface_name
                                    })

                        body_node = child.child_by_field_name("body")
                        if body_node:
                            # Inspect fields for Spring @Autowired or @Inject dependencies
                            for field in body_node.children:
                                if field.type == "field_declaration":
                                    field_anns = extract_annotations(field)
                                    if "Autowired" in field_anns or "Inject" in field_anns:
                                        type_node = field.child_by_field_name("type")
                                        if type_node:
                                            dep_type_name = get_node_text(type_node)
                                            res["injects"].append({
                                                "injector_id": class_id,
                                                "target_class_name": dep_type_name
                                            })

                            traverse(body_node, class_stack + [class_name], func_stack)
                        else:
                            traverse(child, class_stack + [class_name], func_stack)
                    else:
                        traverse(child, class_stack, func_stack)

                elif child.type == "method_declaration":
                    name_node = child.child_by_field_name("name")
                    if name_node:
                        func_name = get_node_text(name_node)
                        qualified_name = f"{class_stack[-1]}.{func_name}" if class_stack else func_name
                        func_id = f"{rel_path}::{qualified_name}"
                        start_line = child.start_point[0] + 1
                        end_line = child.end_point[0] + 1
                        annotations = extract_annotations(child)

                        category = "endpoint" if any(a.endswith("Mapping") for a in annotations) else "method"

                        func_info = {
                            "id": func_id,
                            "name": func_name,
                            "qualified_name": qualified_name,
                            "file_path": rel_path,
                            "start_line": start_line,
                            "end_line": end_line,
                            "category": category
                        }
                        res["functions"].append(func_info)

                        for ann in annotations:
                            res["decorators"].append({
                                "id": f"{func_id}@{ann}",
                                "name": ann,
                                "target_id": func_id,
                                "file_path": rel_path
                            })

                        if class_stack:
                            parent_class_id = f"{rel_path}::{class_stack[-1]}"
                            res["contains"].append({
                                "class_id": parent_class_id,
                                "function_id": func_id
                            })

                        body_node = child.child_by_field_name("body")
                        traverse(body_node or child, class_stack, func_stack + [func_info])
                    else:
                        traverse(child, class_stack, func_stack)

                elif child.type == "method_invocation":
                    if func_stack:
                        caller_func = func_stack[-1]
                        name_node = child.child_by_field_name("name")
                        if name_node:
                            callee_name = get_node_text(name_node)
                            res["calls"].append({
                                "caller_id": caller_func["id"],
                                "callee_name": callee_name
                            })
                    traverse(child, class_stack, func_stack)

                else:
                    traverse(child, class_stack, func_stack)

        traverse(root_node, [], [])
        return res
