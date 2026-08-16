import os
from typing import Dict, List, Any, Optional
import tree_sitter_go as tsgo
from tree_sitter import Language, Parser, Node
from parsers.base import BaseParser


class GoParser(BaseParser):
    def __init__(self):
        self.language = Language(tsgo.language())
        self.parser = Parser(self.language)

    def parse_file(self, file_path: str, code_bytes: bytes) -> Dict[str, List[Dict[str, Any]]]:
        res = self.empty_result()
        rel_path = os.path.relpath(file_path)
        res["files"].append({"id": rel_path, "path": rel_path, "language": "go"})

        try:
            tree = self.parser.parse(code_bytes)
        except Exception as e:
            print(f"Error parsing Go file {file_path}: {e}")
            return res

        root_node = tree.root_node

        def get_node_text(node: Node) -> str:
            return code_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace")

        def extract_callee_name(func_node: Node) -> Optional[str]:
            if func_node.type == "identifier":
                return get_node_text(func_node)
            elif func_node.type == "selector_expression":
                field_child = func_node.child_by_field_name("field")
                if field_child:
                    return get_node_text(field_child)
                return get_node_text(func_node)
            return None

        def traverse(node: Node, func_stack: List[Dict[str, Any]]):
            for child in node.children:
                if child.type == "import_declaration":
                    imp_text = get_node_text(child).strip()
                    res["imports"].append({"file_path": rel_path, "imported_module": imp_text})

                elif child.type == "type_declaration":
                    for spec in child.children:
                        if spec.type == "type_spec":
                            name_node = spec.child_by_field_name("name")
                            type_node = spec.child_by_field_name("type")
                            if name_node:
                                struct_name = get_node_text(name_node)
                                struct_id = f"{rel_path}::{struct_name}"
                                category = "interface" if (type_node and type_node.type == "interface_type") else "struct"
                                res["classes"].append({
                                    "id": struct_id,
                                    "name": struct_name,
                                    "file_path": rel_path,
                                    "category": category
                                })
                    traverse(child, func_stack)

                elif child.type == "method_declaration":
                    name_node = child.child_by_field_name("name")
                    receiver_node = child.child_by_field_name("receiver")
                    if name_node:
                        func_name = get_node_text(name_node)
                        receiver_type = "unknown"
                        if receiver_node:
                            rec_text = get_node_text(receiver_node).strip("()")
                            # Extract type name from e.g. "s *Server" or "s Server"
                            parts = rec_text.rsplit(" ", 1)
                            receiver_type = parts[-1].lstrip("*")

                        qualified_name = f"{receiver_type}.{func_name}" if receiver_type != "unknown" else func_name
                        func_id = f"{rel_path}::{qualified_name}"
                        start_line = child.start_point[0] + 1
                        end_line = child.end_point[0] + 1

                        func_info = {
                            "id": func_id,
                            "name": func_name,
                            "qualified_name": qualified_name,
                            "file_path": rel_path,
                            "start_line": start_line,
                            "end_line": end_line,
                            "category": "method"
                        }
                        res["functions"].append(func_info)

                        if receiver_type != "unknown":
                            parent_class_id = f"{rel_path}::{receiver_type}"
                            res["contains"].append({
                                "class_id": parent_class_id,
                                "function_id": func_id
                            })

                        body_node = child.child_by_field_name("body")
                        traverse(body_node or child, func_stack + [func_info])
                    else:
                        traverse(child, func_stack)

                elif child.type == "function_declaration":
                    name_node = child.child_by_field_name("name")
                    if name_node:
                        func_name = get_node_text(name_node)
                        func_id = f"{rel_path}::{func_name}"
                        start_line = child.start_point[0] + 1
                        end_line = child.end_point[0] + 1

                        func_info = {
                            "id": func_id,
                            "name": func_name,
                            "qualified_name": func_name,
                            "file_path": rel_path,
                            "start_line": start_line,
                            "end_line": end_line,
                            "category": "function"
                        }
                        res["functions"].append(func_info)

                        body_node = child.child_by_field_name("body")
                        traverse(body_node or child, func_stack + [func_info])
                    else:
                        traverse(child, func_stack)

                elif child.type == "call_expression":
                    if func_stack:
                        caller_func = func_stack[-1]
                        func_node = child.child_by_field_name("function")
                        if func_node:
                            callee_name = extract_callee_name(func_node)
                            if callee_name:
                                res["calls"].append({
                                    "caller_id": caller_func["id"],
                                    "callee_name": callee_name
                                })
                    traverse(child, func_stack)

                else:
                    traverse(child, func_stack)

        traverse(root_node, [])
        return res
