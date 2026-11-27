import io
import os
import re
from typing import Any, Dict, List, Optional, Set, Tuple
import pypdf
from parsers.base import BaseParser


STANDARD_HEADINGS = {
    "abstract",
    "introduction",
    "background",
    "related work",
    "preliminaries",
    "methodology",
    "method",
    "methods",
    "approach",
    "architecture",
    "implementation",
    "experiments",
    "experimental setup",
    "evaluation",
    "results",
    "analysis",
    "discussion",
    "limitations",
    "conclusion",
    "conclusions",
    "future work",
    "acknowledgements",
    "acknowledgments",
    "references",
    "bibliography",
    "appendix",
    "overview",
    "summary",
    "table of contents",
}

NUMBERED_HEADING_RE = re.compile(
    r"^(?P<num>(?:\d+(?:\.\d+){0,3}|[A-Z]\.\d+(?:\.\d+)?))\.?\s+(?P<title>[A-Z][A-Za-z0-9\s\-:,/()&]{2,72})$"
)
FIGURE_CAPTION_RE = re.compile(r"^(?:Figure|Fig\.)\s+(\d+[a-zA-Z]?)\s*[:.\-]", re.IGNORECASE)
TABLE_CAPTION_RE = re.compile(r"^(?:Table|Tab\.)\s+(\d+[a-zA-Z]?)\s*[:.\-]", re.IGNORECASE)

FIGURE_REF_RE = re.compile(r"\b(?:Figure|Fig\.)\s+(\d+[a-zA-Z]?)\b", re.IGNORECASE)
TABLE_REF_RE = re.compile(r"\b(?:Table|Tab\.)\s+(\d+[a-zA-Z]?)\b", re.IGNORECASE)
SECTION_REF_RE = re.compile(r"\b(?:Section|Sec\.|§)\s*(\d+(?:\.\d+){0,2})\b", re.IGNORECASE)

URL_RE = re.compile(r"https?://[^\s<>()\"'\]]+")
ARXIV_RE = re.compile(r"\barXiv:\s*(\d{4}\.\d{4,5}(?:v\d+)?)\b", re.IGNORECASE)
DOI_RE = re.compile(r"\b(10\.\d{4,9}/[-._;()/:A-Za-z0-9]+)\b")

MAX_EXTERNAL_REFS = 25


class PdfParser(BaseParser):
    def _clean_url(self, raw: str) -> str:
        return raw.rstrip(".,;:)]}")

    def _short_ref_label(self, ref: str) -> str:
        if ref.startswith("http://") or ref.startswith("https://"):
            stripped = re.sub(r"^https?://(www\.)?", "", ref).rstrip("/")
            if len(stripped) > 42:
                return stripped[:39] + "..."
            return stripped
        return ref

    def _extract_outline_sections(self, reader: pypdf.PdfReader) -> List[Tuple[str, int]]:
        """Extract (title, 1-based page_num) from PDF bookmarks/outline if present."""
        results: List[Tuple[str, int]] = []
        try:
            outline = reader.outline
        except Exception:
            return results

        def _walk(items: Any) -> None:
            if not isinstance(items, list):
                return
            for item in items:
                if isinstance(item, list):
                    _walk(item)
                else:
                    try:
                        title = str(getattr(item, "title", "") or "").strip()
                        if not title or len(title) > 90:
                            continue
                        page_idx = reader.get_destination_page_number(item)
                        if isinstance(page_idx, int) and page_idx >= 0:
                            results.append((title, page_idx + 1))
                    except Exception:
                        continue

        _walk(outline)
        return results

    def _extract_page_annotations_urls(self, page: Any) -> List[str]:
        """Extract clickable URI annotations embedded in a PDF page."""
        urls: List[str] = []
        try:
            annots = page.get("/Annots")
            if not annots:
                return urls
            for annot_ref in annots:
                annot = annot_ref.get_object()
                action = annot.get("/A")
                if action and "/URI" in action:
                    uri = str(action["/URI"]).strip()
                    if uri.startswith(("http://", "https://")):
                        urls.append(self._clean_url(uri))
        except Exception:
            pass
        return urls

    def _detect_heading(self, line: str) -> Optional[Tuple[Optional[str], str]]:
        """Return (section_number_or_None, display_title) if line looks like a section heading."""
        s = re.sub(r"\s+", " ", line).strip()
        if not s or len(s) < 3 or len(s) > 85:
            return None
        # Skip lines that look like sentences, equations, or table rows
        if s.endswith((".", ";", ",")) and not s.lower().rstrip(".") in STANDARD_HEADINGS:
            return None
        if s.count("  ") > 2:
            return None

        if s.lower().rstrip(":") in STANDARD_HEADINGS:
            return None, s.rstrip(":").title()

        m = NUMBERED_HEADING_RE.match(s)
        if m:
            num = m.group("num")
            title = m.group("title").strip()
            # Filter out false positives like dates/years (e.g. "2024 Proceedings...")
            if num.isdigit() and int(num) > 30:
                return None
            # Filter out titles with too many numbers (likely table rows)
            digits = sum(ch.isdigit() for ch in title)
            if digits > max(4, len(title) // 3):
                return None
            return num, f"{num} {title}"

        return None

    def parse_file(
        self,
        file_path: str,
        code_bytes: bytes,
        base_dir: Optional[str] = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        res = self.empty_result()
        rel_path = self.get_rel_path(file_path, base_dir)
        res["files"].append({"id": rel_path, "path": rel_path, "language": "pdf"})

        pdf_name = os.path.basename(file_path)
        doc_id = f"{rel_path}::{pdf_name}"

        res["classes"].append({
            "id": doc_id,
            "name": pdf_name,
            "file_path": rel_path,
            "category": "pdf_document",
        })

        try:
            reader = pypdf.PdfReader(io.BytesIO(code_bytes))
            num_pages = len(reader.pages)
        except Exception as e:
            print(f"Error reading PDF file {file_path}: {e}")
            return res

        seen_func_ids: Set[str] = set()
        seen_calls: Set[Tuple[str, str]] = set()
        seen_imports: Set[str] = set()

        def add_function(func_id: str, name: str, page_num: int, category: str) -> None:
            if func_id in seen_func_ids:
                return
            seen_func_ids.add(func_id)
            res["functions"].append({
                "id": func_id,
                "name": name,
                "qualified_name": f"{pdf_name} > {name}",
                "file_path": rel_path,
                "start_line": page_num,
                "end_line": page_num,
                "category": category,
            })
            res["contains"].append({
                "class_id": doc_id,
                "function_id": func_id,
            })

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

        def add_import(target: str) -> None:
            if target not in seen_imports:
                seen_imports.add(target)
                res["imports"].append({
                    "file_path": rel_path,
                    "imported_module": target,
                })

        # Track sections, figures, tables, and external references across all pages
        section_num_to_name: Dict[str, str] = {}
        section_num_to_id: Dict[str, str] = {}
        figure_names: Set[str] = set()
        table_names: Set[str] = set()
        external_ref_count = 0

        # Pre-seed sections from PDF outline/bookmarks if available
        outline_by_page: Dict[int, List[str]] = {}
        for title, pnum in self._extract_outline_sections(reader):
            outline_by_page.setdefault(pnum, []).append(title)

        page_texts: List[str] = []
        page_section_map: List[Tuple[str, str, str]] = []  # (owner_id, owner_name, text_block)
        active_section_id: Optional[str] = None

        for page_idx in range(num_pages):
            page_num = page_idx + 1
            page = reader.pages[page_idx]
            try:
                text = page.extract_text() or ""
            except Exception:
                text = ""
            page_texts.append(text)

            page_name = f"Page_{page_num}"
            page_id = f"{doc_id}::{page_name}"
            add_function(page_id, page_name, page_num, "pdf_page")

            # Register outline sections starting on this page
            for title in outline_by_page.get(page_num, []):
                sec_id = f"{doc_id}::sec::{title}"
                add_function(sec_id, title, page_num, "pdf_section")
                add_call(page_id, title)
                m_num = re.match(r"^(\d+(?:\.\d+){0,3}|[A-Z]\.\d+)\b", title)
                if m_num:
                    num = m_num.group(1)
                    section_num_to_name[num] = title
                    section_num_to_id[num] = sec_id
                active_section_id = sec_id

            # Scan lines for headings, figures, and tables
            current_owner_id = active_section_id or page_id
            current_block_lines: List[str] = []

            for raw_line in text.splitlines():
                line = raw_line.strip()
                if not line:
                    continue

                # Figure caption
                fig_match = FIGURE_CAPTION_RE.match(line)
                if fig_match:
                    fig_name = f"Figure {fig_match.group(1)}"
                    fig_id = f"{doc_id}::fig::{fig_match.group(1)}"
                    figure_names.add(fig_name)
                    add_function(fig_id, fig_name, page_num, "pdf_figure")
                    add_call(current_owner_id, fig_name)
                    if current_owner_id != page_id:
                        add_call(page_id, fig_name)
                    continue

                # Table caption
                tab_match = TABLE_CAPTION_RE.match(line)
                if tab_match:
                    tab_name = f"Table {tab_match.group(1)}"
                    tab_id = f"{doc_id}::tab::{tab_match.group(1)}"
                    table_names.add(tab_name)
                    add_function(tab_id, tab_name, page_num, "pdf_table")
                    add_call(current_owner_id, tab_name)
                    if current_owner_id != page_id:
                        add_call(page_id, tab_name)
                    continue

                # Section heading
                heading = self._detect_heading(line)
                if heading:
                    if current_block_lines:
                        page_section_map.append((current_owner_id, page_id, "\n".join(current_block_lines)))
                        current_block_lines = []

                    sec_num, sec_title = heading
                    sec_id = f"{doc_id}::sec::{sec_title}"
                    add_function(sec_id, sec_title, page_num, "pdf_section")
                    add_call(page_id, sec_title)

                    if sec_num:
                        section_num_to_name[sec_num] = sec_title
                        section_num_to_id[sec_num] = sec_id
                        # Link subsection (e.g. 2.1) from parent section (e.g. 2)
                        if "." in sec_num:
                            parent_num = sec_num.rsplit(".", 1)[0]
                            parent_id = section_num_to_id.get(parent_num)
                            if parent_id and parent_id != sec_id:
                                add_call(parent_id, sec_title)

                    active_section_id = sec_id
                    current_owner_id = sec_id
                    continue

                current_block_lines.append(line)

            if current_block_lines:
                page_section_map.append((current_owner_id, page_id, "\n".join(current_block_lines)))

            # Extract URLs from annotations and page text
            page_urls = self._extract_page_annotations_urls(page)
            for url_match in URL_RE.finditer(text):
                page_urls.append(self._clean_url(url_match.group(0)))

            for url in page_urls:
                add_import(url)
                if external_ref_count < MAX_EXTERNAL_REFS:
                    ref_label = self._short_ref_label(url)
                    ref_id = f"{doc_id}::ref::{ref_label}"
                    if ref_id not in seen_func_ids:
                        external_ref_count += 1
                        add_function(ref_id, ref_label, page_num, "pdf_reference")
                    add_call(active_section_id or page_id, ref_label)

            # Extract arXiv IDs and DOIs
            for arxiv_match in ARXIV_RE.finditer(text):
                arxiv_label = f"arXiv:{arxiv_match.group(1)}"
                add_import(arxiv_label)
                if external_ref_count < MAX_EXTERNAL_REFS:
                    ref_id = f"{doc_id}::ref::{arxiv_label}"
                    if ref_id not in seen_func_ids:
                        external_ref_count += 1
                        add_function(ref_id, arxiv_label, page_num, "pdf_reference")
                    add_call(active_section_id or page_id, arxiv_label)

            for doi_match in DOI_RE.finditer(text):
                doi_label = f"doi:{doi_match.group(1).rstrip('.')}"
                add_import(doi_label)
                if external_ref_count < MAX_EXTERNAL_REFS:
                    ref_id = f"{doc_id}::ref::{doi_label}"
                    if ref_id not in seen_func_ids:
                        external_ref_count += 1
                        add_function(ref_id, doi_label, page_num, "pdf_reference")
                    add_call(active_section_id or page_id, doi_label)

        # Second pass: resolve cross-references (Figure N, Table N, Section N)
        for owner_id, _page_id, block_text in page_section_map:
            for m in FIGURE_REF_RE.finditer(block_text):
                target = f"Figure {m.group(1)}"
                if target in figure_names:
                    add_call(owner_id, target)

            for m in TABLE_REF_RE.finditer(block_text):
                target = f"Table {m.group(1)}"
                if target in table_names:
                    add_call(owner_id, target)

            for m in SECTION_REF_RE.finditer(block_text):
                sec_num = m.group(1)
                target = section_num_to_name.get(sec_num)
                if target and section_num_to_id.get(sec_num) != owner_id:
                    add_call(owner_id, target)

        return res
