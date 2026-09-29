import os
from typing import Dict, List, Any, Optional
import tree_sitter_javascript as tsjs
from tree_sitter import Language, Parser, Node
from parsers.base import BaseParser


class JavaScriptParser(BaseParser):
    def __init__(self):
        self.js_language = Language(tsjs.language())
        self.js_parser = Parser(self.js_language)

    def parse_file(self, file_path: str, code_bytes: bytes) -> Dict[str, List[Dict[str, Any]]]:
        res = self.empty_result()
        rel_path = os.path.relpath(file_path)
        is_jsx = file_path.endswith(".jsx") or file_path.endswith(".cjsx") or file_path.endswith(".mjsx")
        lang_label = "jsx" if is_jsx else "javascript"

        res["files"].append({"id": rel_path, "path": rel_path, "language": lang_label})

        try:
            tree = self.js_parser.parse(code_bytes)
        except Exception as e:
            print(f"Error parsing JavaScript/JSX file {file_path}: {e}")
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

        def extract_jsx_tag_name(jsx_node: Node) -> Optional[str]:
            if jsx_node.type == "jsx_element":
                for c in jsx_node.children:
                    if c.type == "jsx_opening_element":
                        for gc in c.children:
                            if gc.type in ("identifier", "nested_identifier", "member_expression"):
                                return get_node_text(gc)
            elif jsx_node.type == "jsx_self_closing_element":
                for gc in jsx_node.children:
                    if gc.type in ("identifier", "nested_identifier", "member_expression"):
                        return get_node_text(gc)
            return None

        def extract_func_name(node: Node) -> Optional[str]:
            name_node = node.child_by_field_name("name")
            if name_node:
                return get_node_text(name_node)

            parent = node.parent
            if not parent:
                return None

            if parent.type == "variable_declarator":
                var_name = parent.child_by_field_name("name")
                if var_name:
                    return get_node_text(var_name)
            elif parent.type == "pair":
                key_node = parent.child_by_field_name("key")
                if key_node:
                    return get_node_text(key_node)
            elif parent.type == "assignment_expression":
                left = parent.child_by_field_name("left")
                if left:
                    if left.type == "member_expression":
                        prop = left.child_by_field_name("property")
                        if prop:
                            return get_node_text(prop)
                    return get_node_text(left)
            elif parent.type == "arguments" and parent.parent and parent.parent.type == "call_expression":
                call_expr = parent.parent
                if call_expr.parent and call_expr.parent.type == "variable_declarator":
                    var_name = call_expr.parent.child_by_field_name("name")
                    if var_name:
                        return get_node_text(var_name)
                elif call_expr.parent and call_expr.parent.type == "assignment_expression":
                    left = call_expr.parent.child_by_field_name("left")
                    if left:
                        if left.type == "member_expression":
                            prop = left.child_by_field_name("property")
                            if prop:
                                return get_node_text(prop)
                        return get_node_text(left)
            return None

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
                    traverse(child, class_stack, func_stack, pending_decorators)
                    pending_decorators = []

                elif child.type in ("class_declaration", "class"):
                    name_node = child.child_by_field_name("name")
                    class_name = get_node_text(name_node) if name_node else None

                    if not class_name and child.parent and child.parent.type == "variable_declarator":
                        var_name_node = child.parent.child_by_field_name("name")
                        if var_name_node:
                            class_name = get_node_text(var_name_node)

                    if class_name:
                        class_id = f"{rel_path}::{class_name}"
                        decorators = list(set(pending_decorators + extract_decorator_names(child.children)))
                        pending_decorators = []

                        category = "class"
                        if "Controller" in decorators or class_name.endswith("Controller"):
                            category = "controller"
                        elif "Injectable" in decorators or "Service" in class_name:
                            category = "service"
                        elif "Module" in decorators or class_name.endswith("Module"):
                            category = "module"

                        # Check class heritage for extends / implements
                        for c in child.children:
                            if c.type == "class_heritage":
                                for h_child in c.children:
                                    if h_child.type in ("identifier", "member_expression"):
                                        base_name = get_node_text(h_child)
                                        if base_name and base_name != "extends":
                                            res["implements"].append({
                                                "class_id": class_id,
                                                "interface_name": base_name
                                            })
                                            if base_name in ("Component", "PureComponent", "React.Component", "React.PureComponent"):
                                                category = "component"
                                    elif h_child.type in ("extends_clause", "extends"):
                                        for sub_c in h_child.children:
                                            if sub_c.type in ("identifier", "member_expression"):
                                                base_name = get_node_text(sub_c)
                                                if base_name and base_name != "extends":
                                                    res["implements"].append({
                                                        "class_id": class_id,
                                                        "interface_name": base_name
                                                    })
                                                    if base_name in ("Component", "PureComponent", "React.Component", "React.PureComponent"):
                                                        category = "component"
                                    elif h_child.type == "implements_clause":
                                        for iface_node in h_child.children:
                                            if iface_node.type in ("type_identifier", "generic_type", "identifier"):
                                                iface_name = get_node_text(iface_node).split("<")[0].strip()
                                                if iface_name and iface_name != "implements":
                                                    res["implements"].append({
                                                        "class_id": class_id,
                                                        "interface_name": iface_name
                                                    })

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

                        body_node = child.child_by_field_name("body")
                        traverse(body_node or child, class_stack + [class_name], func_stack)
                    else:
                        traverse(child, class_stack, func_stack)
                    pending_decorators = []

                elif child.type in ("function_declaration", "generator_function_declaration", "method_definition", "arrow_function", "function_expression"):
                    func_name = extract_func_name(child)

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
                    rendered_comp = extract_jsx_tag_name(child)
                    if rendered_comp and rendered_comp[0].isupper() and func_stack:
                        caller_func = func_stack[-1]
                        res["renders"].append({
                            "parent_func_id": caller_func["id"],
                            "rendered_component_name": rendered_comp
                        })
                    traverse(child, class_stack, func_stack)

                elif child.type == "call_expression":
                    func_node = child.child_by_field_name("function")
                    callee_name = extract_callee_name(func_node) if func_node else None

                    # Extract CommonJS require('...') or dynamic import('...') as imports
                    if callee_name in ("require", "import"):
                        args_node = child.child_by_field_name("arguments")
                        if args_node and args_node.children:
                            for arg in args_node.children:
                                if arg.type in ("string", "template_string"):
                                    mod_name = get_node_text(arg).strip("'\"`")
                                    res["imports"].append({
                                        "file_path": rel_path,
                                        "imported_module": mod_name
                                    })
                                    break

                    if func_stack and callee_name:
                        caller_func = func_stack[-1]
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
