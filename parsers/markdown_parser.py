import os
import re
from typing import Dict, List, Any
from parsers.base import BaseParser


class MarkdownParser(BaseParser):
    def parse_file(self, file_path: str, code_bytes: bytes) -> Dict[str, List[Dict[str, Any]]]:
        res = self.empty_result()
        rel_path = os.path.relpath(file_path)
        res["files"].append({"id": rel_path, "path": rel_path, "language": "markdown"})

        doc_name = os.path.basename(file_path)
        doc_id = f"{rel_path}::{doc_name}"
        res["classes"].append({
            "id": doc_id,
            "name": doc_name,
            "file_path": rel_path,
            "category": "document"
        })

        try:
            text = code_bytes.decode("utf-8", errors="replace")
        except Exception as e:
            print(f"Error reading Markdown file {file_path}: {e}")
            return res

        lines = text.splitlines()

        current_section = doc_name
        current_section_id = doc_id

        link_regex = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
        heading_regex = re.compile(r"^(#{1,6})\s+(.+)$")

        for idx, line in enumerate(lines, start=1):
            line_str = line.strip()

            # 1. Heading extraction
            heading_match = heading_regex.match(line_str)
            if heading_match:
                level = len(heading_match.group(1))
                title = heading_match.group(2).strip()
                sec_id = f"{rel_path}::H{level}_{title}"

                res["functions"].append({
                    "id": sec_id,
                    "name": title,
                    "qualified_name": f"{doc_name} > {title}",
                    "file_path": rel_path,
                    "start_line": idx,
                    "end_line": idx,
                    "category": "section"
                })

                res["contains"].append({
                    "class_id": doc_id,
                    "function_id": sec_id
                })

                current_section = title
                current_section_id = sec_id

            # 2. Markdown Link extraction e.g. [label](path/to/target)
            for match in link_regex.finditer(line_str):
                link_label, link_target = match.group(1), match.group(2)
                if not link_target.startswith(("http://", "https://", "#")):
                    # Internal relative file link reference
                    target_name = os.path.basename(link_target)
                    res["imports"].append({
                        "file_path": rel_path,
                        "imported_module": link_target
                    })
                    res["calls"].append({
                        "caller_id": current_section_id if current_section_id != doc_id else doc_id,
                        "callee_name": target_name
                    })

        return res
