import os
import io
import re
from typing import Dict, List, Any
import pypdf
from parsers.base import BaseParser


class PdfParser(BaseParser):
    def parse_file(self, file_path: str, code_bytes: bytes) -> Dict[str, List[Dict[str, Any]]]:
        res = self.empty_result()
        rel_path = os.path.relpath(file_path)
        res["files"].append({"id": rel_path, "path": rel_path, "language": "pdf"})

        pdf_name = os.path.basename(file_path)
        doc_id = f"{rel_path}::{pdf_name}"

        res["classes"].append({
            "id": doc_id,
            "name": pdf_name,
            "file_path": rel_path,
            "category": "pdf_document"
        })

        try:
            reader = pypdf.PdfReader(io.BytesIO(code_bytes))
            num_pages = len(reader.pages)
        except Exception as e:
            print(f"Error reading PDF file {file_path}: {e}")
            return res

        link_regex = re.compile(r"https?://[^\s>]+")

        for page_num in range(num_pages):
            try:
                page = reader.pages[page_num]
                text = page.extract_text() or ""
            except Exception:
                text = ""

            page_name = f"Page_{page_num + 1}"
            page_id = f"{doc_id}::{page_name}"

            res["functions"].append({
                "id": page_id,
                "name": page_name,
                "qualified_name": f"{pdf_name} > {page_name}",
                "file_path": rel_path,
                "start_line": page_num + 1,
                "end_line": page_num + 1,
                "category": "pdf_page"
            })

            res["contains"].append({
                "class_id": doc_id,
                "function_id": page_id
            })

            # Link extraction from page text
            for link_match in link_regex.finditer(text):
                url = link_match.group(0)
                res["imports"].append({
                    "file_path": rel_path,
                    "imported_module": url
                })

        return res
