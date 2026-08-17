import os
from typing import Dict, List, Any, Optional
import tree_sitter_typescript as tsts
from tree_sitter import Language, Parser, Node
from parsers.base import BaseParser


class TypeScriptParser(BaseParser):
    def __init__(self):
        self.ts_language = Language(tsts.language_typescript())
        self.tsx_language = Language(tsts.language_tsx())
        self.ts_parser = Parser(self.ts_language)
        self.tsx_parser = Parser(self.tsx_language)

    def parse_file(self, file_path: str, code_bytes: bytes) -> Dict[str, List[Dict[str, Any]]]:
        res = self.empty_result()
        rel_path = os.path.relpath(file_path)
        is_tsx = file_path.endswith(".tsx") or file_path.endswith(".jsx")
        parser = self.tsx_parser if is_tsx else self.ts_parser
        lang_label = "tsx" if is_tsx else "typescript"

        res["files"].append({"id": rel_path, "path": rel_path, "language": lang_label})

        try:
            tree = parser.parse(code_bytes)
        except Exception as e:
            print(f"Error parsing TS/JS file {file_path}: {e}")
            return res

        root_node = tree.root_node

        def get_node_text(node: Node) -> str:
            return code_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace")

        def extract_callee_name(func_node: Node) -> Optional[str]:
            if func_node.type == "identifier":
                return get_node_text(func_node)
            elif func_node.type == "member_expression":
                property_child = func_node.child_by_field_name("property")
                if property_child:
                    return get_node_text(property_child)
                return get_node_text(func_node)
            return None

        def extract_decorator_names(nodes: List[Node]) -> List[str]:
            decorators = []
            for n in nodes:
                if n.type == "decorator":
                    dec_text = get_node_text(n).strip("@ ")
                    dec_name = dec_text.split("(")[0].strip()
                    decorators.append(dec_name)
            return decorators

        def traverse(node: Node, class_stack: List[str], func_stack: List[Dict[str, Any]], pending_decorators: List[str] = None):
            if pending_decorators is None:
                pending_decorators = []

            children = list(node.children)
            i = 0
            while i < len(children):
                child = children[i]

                if child.type == "decorator":
                    dec_text = get_node_text(child).strip("@ ")
                    dec_name = dec_text.split("(")[0].strip()
                    pending_decorators.append(dec_name)
                    i += 1
                    continue

                elif child.type == "import_statement":
                    imp_text = get_node_text(child).strip()
                    res["imports"].append({"file_path": rel_path, "imported_module": imp_text})
                    pending_decorators = []

                elif child.type == "export_statement":
                    # Traverse export statement passing any collected decorators
                    traverse(child, class_stack, func_stack, pending_decorators)
                    pending_decorators = []

                elif child.type == "class_declaration":
                    name_node = child.child_by_field_name("name")
                    if name_node:
                        class_name = get_node_text(name_node)
                        class_id = f"{rel_path}::{class_name}"
                        decorators = list(set(pending_decorators + extract_decorator_names(child.children)))
                        pending_decorators = []

                        category = "class"
                        if "Controller" in decorators:
                            category = "controller"
                        elif "Injectable" in decorators or "Service" in class_name:
                            category = "service"
                        elif "Module" in decorators:
                            category = "module"

                        res["classes"].append({
                            "id": class_id,
                            "name": class_name,
                            "file_path": rel_path,
                            "category": category
                        })

                        for dec in decorators:
                            res["decorators"].append({
                                "id": f"{class_id}@{dec}",
                                "name": dec,
                                "target_id": class_id,
                                "file_path": rel_path
                            })

                        # Extract interfaces implemented
                        for c in child.children:
                            if c.type == "class_heritage":
                                for h_child in c.children:
                                    if h_child.type == "implements_clause":
                                        for iface_node in h_child.children:
                                            if iface_node.type in ("type_identifier", "generic_type"):
                                                iface_name = get_node_text(iface_node).split("<")[0].strip()
                                                if iface_name and iface_name != "implements":
                                                    res["implements"].append({
                                                        "class_id": class_id,
                                                        "interface_name": iface_name
                                                    })

                        # Extract NestJS Constructor Dependency Injection
                        body_node = child.child_by_field_name("body")
                        if body_node:
                            for m in body_node.children:
                                if m.type == "method_definition":
                                    m_name_node = m.child_by_field_name("name")
                                    if m_name_node and get_node_text(m_name_node) == "constructor":
                                        params_node = m.child_by_field_name("parameters")
                                        if params_node:
                                            def find_type_identifiers(p_node: Node) -> List[str]:
                                                found = []
                                                if p_node.type == "type_identifier":
                                                    found.append(get_node_text(p_node))
                                                for c_node in p_node.children:
                                                    found.extend(find_type_identifiers(c_node))
                                                return found

                                            for param in params_node.children:
                                                for target_dep_name in find_type_identifiers(param):
                                                    if target_dep_name and target_dep_name != class_name:
                                                        res["injects"].append({
                                                            "injector_id": class_id,
                                                            "target_class_name": target_dep_name
                                                        })

                        traverse(body_node or child, class_stack + [class_name], func_stack)
                    else:
                        traverse(child, class_stack, func_stack)
                    pending_decorators = []

                elif child.type in ("function_declaration", "method_definition", "arrow_function"):
                    name_node = child.child_by_field_name("name")
                    func_name = get_node_text(name_node) if name_node else None

                    if not func_name and child.parent and child.parent.type == "variable_declarator":
                        var_name_node = child.parent.child_by_field_name("name")
                        if var_name_node:
                            func_name = get_node_text(var_name_node)

                    if func_name:
                        qualified_name = f"{class_stack[-1]}.{func_name}" if class_stack else func_name
                        func_id = f"{rel_path}::{qualified_name}"
                        start_line = child.start_point[0] + 1
                        end_line = child.end_point[0] + 1
                        decorators = list(set(pending_decorators + extract_decorator_names(child.children)))
                        pending_decorators = []

                        category = "function"
                        if class_stack:
                            category = "method"
                        elif func_name.startswith("use") and func_name[3:4].isupper():
                            category = "hook"
                        elif func_name[0].isupper() or is_tsx:
                            category = "component"

                        if any(d in ("Get", "Post", "Put", "Delete", "Patch") for d in decorators):
                            category = "endpoint"

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

                        for dec in decorators:
                            res["decorators"].append({
                                "id": f"{func_id}@{dec}",
                                "name": dec,
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
                    pending_decorators = []

                elif child.type in ("jsx_element", "jsx_self_closing_element"):
                    open_tag = child.child_by_field_name("open_tag") if child.type == "jsx_element" else child
                    if open_tag:
                        tag_name_node = open_tag.child_by_field_name("name")
                        if tag_name_node:
                            rendered_comp = get_node_text(tag_name_node)
                            if rendered_comp and rendered_comp[0].isupper() and func_stack:
                                caller_func = func_stack[-1]
                                res["renders"].append({
                                    "parent_func_id": caller_func["id"],
                                    "rendered_component_name": rendered_comp
                                })
                    traverse(child, class_stack, func_stack)

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
                    traverse(child, class_stack, func_stack)

                else:
                    traverse(child, class_stack, func_stack)

                i += 1

        traverse(root_node, [], [])
        return res
