import os
from typing import Dict, List, Any, Optional
import tree_sitter_python as tspython
from tree_sitter import Language, Parser, Node
from parsers.base import BaseParser


class PythonParser(BaseParser):
    def __init__(self):
        self.language = Language(tspython.language())
        self.parser = Parser(self.language)

    def parse_file(self, file_path: str, code_bytes: bytes) -> Dict[str, List[Dict[str, Any]]]:
        res = self.empty_result()
        rel_path = os.path.relpath(file_path)
        res["files"].append({"id": rel_path, "path": rel_path, "language": "python"})

        try:
            tree = self.parser.parse(code_bytes)
        except Exception as e:
            print(f"Error parsing Python file {file_path}: {e}")
            return res

        root_node = tree.root_node

        def get_node_text(node: Node) -> str:
            return code_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace")

        def get_callee_name(func_node: Node) -> Optional[str]:
            if func_node.type == "identifier":
                return get_node_text(func_node)
            elif func_node.type == "attribute":
                attribute_child = func_node.child_by_field_name("attribute")
                if attribute_child:
                    return get_node_text(attribute_child)
                return get_node_text(func_node)
            return None

        def extract_fastapi_depends(param_node: Node, func_info: Dict[str, Any]):
            """Extracts Depends(dependency_name) from FastAPI parameters."""
            for child in param_node.children:
                if child.type == "call":
                    func_child = child.child_by_field_name("function")
                    if func_child and get_node_text(func_child) == "Depends":
                        args_child = child.child_by_field_name("arguments")
                        if args_child:
                            for arg in args_child.children:
                                if arg.type in ("identifier", "attribute"):
                                    dep_name = get_node_text(arg)
                                    res["injects"].append({
                                        "injector_id": func_info["id"],
                                        "target_class_name": dep_name
                                    })
                                    res["calls"].append({
                                        "caller_id": func_info["id"],
                                        "callee_name": dep_name
                                    })

        def traverse(node: Node, class_stack: List[str], func_stack: List[Dict[str, Any]]):
            for child in node.children:
                if child.type == "import_statement":
                    imp_text = get_node_text(child).strip()
                    res["imports"].append({"file_path": rel_path, "imported_module": imp_text})

                elif child.type == "import_from_statement":
                    imp_text = get_node_text(child).strip()
                    res["imports"].append({"file_path": rel_path, "imported_module": imp_text})

                elif child.type == "class_definition":
                    name_node = child.child_by_field_name("name")
                    if name_node:
                        class_name = get_node_text(name_node)
                        class_id = f"{rel_path}::{class_name}"
                        res["classes"].append({
                            "id": class_id,
                            "name": class_name,
                            "file_path": rel_path,
                            "category": "class"
                        })
                        body_node = child.child_by_field_name("body")
                        traverse(body_node or child, class_stack + [class_name], func_stack)
                    else:
                        traverse(child, class_stack, func_stack)

                elif child.type in ("function_definition", "async_function_definition"):
                    name_node = child.child_by_field_name("name")
                    if name_node:
                        func_name = get_node_text(name_node)
                        qualified_name = f"{class_stack[-1]}.{func_name}" if class_stack else func_name
                        func_id = f"{rel_path}::{qualified_name}"
                        start_line = child.start_point[0] + 1
                        end_line = child.end_point[0] + 1

                        category = "method" if class_stack else "function"

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

                        if class_stack:
                            parent_class_id = f"{rel_path}::{class_stack[-1]}"
                            res["contains"].append({
                                "class_id": parent_class_id,
                                "function_id": func_id
                            })

                        # Check parameters for FastAPI Depends(...)
                        params_node = child.child_by_field_name("parameters")
                        if params_node:
                            for p in params_node.children:
                                if p.type in ("default_parameter", "typed_default_parameter"):
                                    extract_fastapi_depends(p, func_info)

                        body_node = child.child_by_field_name("body")
                        traverse(body_node or child, class_stack, func_stack + [func_info])
                    else:
                        traverse(child, class_stack, func_stack)

                elif child.type == "decorated_definition":
                    definition_child = child.child_by_field_name("definition")
                    decorators = []
                    is_fastapi_endpoint = False

                    for c in child.children:
                        if c.type == "decorator":
                            dec_str = get_node_text(c).strip("@ ")
                            decorators.append(dec_str)
                            # Check FastAPI route decorator e.g. app.get("/"), router.post("/items")
                            if any(dec_str.startswith(prefix) for prefix in ("app.get", "app.post", "app.put", "app.delete", "app.patch", "router.get", "router.post", "router.put", "router.delete", "router.patch")):
                                is_fastapi_endpoint = True

                    if definition_child:
                        # Extract inner definition with updated category if endpoint
                        name_node = definition_child.child_by_field_name("name")
                        if name_node and definition_child.type in ("function_definition", "async_function_definition"):
                            func_name = get_node_text(name_node)
                            qualified_name = f"{class_stack[-1]}.{func_name}" if class_stack else func_name
                            func_id = f"{rel_path}::{qualified_name}"
                            start_line = definition_child.start_point[0] + 1
                            end_line = definition_child.end_point[0] + 1

                            func_info = {
                                "id": func_id,
                                "name": func_name,
                                "qualified_name": qualified_name,
                                "file_path": rel_path,
                                "start_line": start_line,
                                "end_line": end_line,
                                "category": "endpoint" if is_fastapi_endpoint else ("method" if class_stack else "function")
                            }
                            res["functions"].append(func_info)

                            for dec in decorators:
                                res["decorators"].append({
                                    "id": f"{func_id}@{dec}",
                                    "name": dec,
                                    "target_id": func_id,
                                    "file_path": rel_path
                                })

                            params_node = definition_child.child_by_field_name("parameters")
                            if params_node:
                                for p in params_node.children:
                                    if p.type in ("default_parameter", "typed_default_parameter"):
                                        extract_fastapi_depends(p, func_info)

                            body_node = definition_child.child_by_field_name("body")
                            traverse(body_node or definition_child, class_stack, func_stack + [func_info])
                        else:
                            traverse(child, class_stack, func_stack)
                    else:
                        traverse(child, class_stack, func_stack)

                elif child.type == "call":
                    if func_stack:
                        caller_func = func_stack[-1]
                        func_node = child.child_by_field_name("function")
                        if func_node:
                            callee_name = get_callee_name(func_node)
                            if callee_name:
                                res["calls"].append({
                                    "caller_id": caller_func["id"],
                                    "callee_name": callee_name
                                })
                    traverse(child, class_stack, func_stack)

                else:
                    traverse(child, class_stack, func_stack)

        traverse(root_node, [], [])
        return res
