import os
import re
from typing import Any, Dict, List, Optional, Set, Tuple
from parsers.base import BaseParser


def _slugify_heading(title: str) -> str:
    slug = title.strip().lower()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s]+", "-", slug)
    return slug


class MarkdownParser(BaseParser):
    def parse_file(
        self,
        file_path: str,
        code_bytes: bytes,
        base_dir: Optional[str] = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        res = self.empty_result()
        rel_path = self.get_rel_path(file_path, base_dir)
        res["files"].append({"id": rel_path, "path": rel_path, "language": "markdown"})

        doc_name = os.path.basename(file_path)
        doc_id = f"{rel_path}::{doc_name}"
        res["classes"].append({
            "id": doc_id,
            "name": doc_name,
            "file_path": rel_path,
            "category": "document",
        })

        try:
            text = code_bytes.decode("utf-8", errors="replace")
        except Exception as e:
            print(f"Error reading Markdown file {file_path}: {e}")
            return res

        lines = text.splitlines()
        total_lines = len(lines)

        link_regex = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
        wiki_link_regex = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")
        heading_regex = re.compile(r"^(#{1,6})\s+(.+?)(?:\s+#+\s*)?$")

        seen_calls: Set[Tuple[str, str]] = set()
        seen_imports: Set[str] = set()

        def add_call(caller_id: str, callee_name: str) -> None:
            if not caller_id or not callee_name:
                return
            key = (caller_id, callee_name)
            if key not in seen_calls:
                seen_calls.add(key)
                res["calls"].append({
                    "caller_id": caller_id,
                    "callee_name": callee_name,
                })

        # Stack of (level, sec_id, title, func_dict) for hierarchy & end_line tracking
        heading_stack: List[Tuple[int, str, str, Dict[str, Any]]] = []
        slug_to_title: Dict[str, str] = {}
        pending_anchor_refs: List[Tuple[str, str]] = []  # (caller_id, slug)

        current_section_id = doc_id
        in_code_fence = False

        for idx, line in enumerate(lines, start=1):
            line_str = line.strip()

            if line_str.startswith("```") or line_str.startswith("~~~"):
                in_code_fence = not in_code_fence
                continue
            if in_code_fence:
                continue

            # 1. Heading extraction with hierarchy & section line spans
            heading_match = heading_regex.match(line_str)
            if heading_match:
                level = len(heading_match.group(1))
                title = heading_match.group(2).strip()
                sec_id = f"{rel_path}::H{level}_{title}"

                # Close any open headings at same or deeper level
                while heading_stack and heading_stack[-1][0] >= level:
                    _, _, _, prev_func = heading_stack.pop()
                    prev_func["end_line"] = max(prev_func["start_line"], idx - 1)

                func_entry = {
                    "id": sec_id,
                    "name": title,
                    "qualified_name": f"{doc_name} > {title}",
                    "file_path": rel_path,
                    "start_line": idx,
                    "end_line": total_lines,
                    "category": "section",
                }
                res["functions"].append(func_entry)
                res["contains"].append({
                    "class_id": doc_id,
                    "function_id": sec_id,
                })

                # Link parent heading -> child heading
                if heading_stack:
                    parent_id = heading_stack[-1][1]
                    add_call(parent_id, title)

                heading_stack.append((level, sec_id, title, func_entry))
                slug_to_title[_slugify_heading(title)] = title
                current_section_id = sec_id
                continue

            # 2. Markdown Link extraction e.g. [label](path/to/target) or [label](#anchor)
            for match in link_regex.finditer(line_str):
                _link_label, link_target = match.group(1), match.group(2).strip()
                if link_target.startswith("#"):
                    anchor_slug = link_target[1:].strip().lower()
                    if anchor_slug:
                        pending_anchor_refs.append((current_section_id, anchor_slug))
                elif not link_target.startswith(("http://", "https://", "mailto:")):
                    clean_target = link_target.split("#", 1)[0]
                    if clean_target:
                        target_name = os.path.basename(clean_target)
                        if clean_target not in seen_imports:
                            seen_imports.add(clean_target)
                            res["imports"].append({
                                "file_path": rel_path,
                                "imported_module": clean_target,
                            })
                        add_call(current_section_id, target_name)

            # 3. Wiki-links e.g. [[Architecture]] or [[Note#Section]]
            for wmatch in wiki_link_regex.finditer(line_str):
                raw_target = wmatch.group(1).strip()
                if "#" in raw_target:
                    page_part, sec_part = raw_target.split("#", 1)
                    if sec_part.strip():
                        add_call(current_section_id, sec_part.strip())
                    if page_part.strip():
                        add_call(current_section_id, page_part.strip())
                elif raw_target:
                    add_call(current_section_id, raw_target)

        # Resolve internal #anchor links to matching section titles
        for caller_id, anchor_slug in pending_anchor_refs:
            target_title = slug_to_title.get(anchor_slug)
            if target_title:
                add_call(caller_id, target_title)

        return res
