import io
from pypdf import PdfWriter
from parsers.pdf_parser import PdfParser


def test_parse_pdf_pages_and_links():
    # Generate a simple in-memory PDF
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)

    pdf_bytes_io = io.BytesIO()
    writer.write(pdf_bytes_io)
    pdf_bytes = pdf_bytes_io.getvalue()

    parser = PdfParser()
    res = parser.parse_file("report.pdf", pdf_bytes)

    docs = [c["name"] for c in res["classes"] if c["category"] == "pdf_document"]
    assert "report.pdf" in docs

    pages = [f["name"] for f in res["functions"] if f["category"] == "pdf_page"]
    assert "Page_1" in pages


def test_parse_pdf_sections_figures_tables_and_cross_refs(monkeypatch):
    class FakePage:
        def __init__(self, text):
            self._text = text

        def extract_text(self):
            return self._text

        def get(self, _key, default=None):
            return default

    class FakeReader:
        outline = []

        def __init__(self, _stream):
            self.pages = [
                FakePage(
                    "Abstract\n"
                    "We introduce a graph engine as shown in Figure 1 and Section 2.\n"
                    "1 Introduction\n"
                    "See Table 1 for benchmarks and arXiv:2601.15153v1 for details.\n"
                    "Figure 1: System Architecture\n"
                ),
                FakePage(
                    "2 Methodology\n"
                    "2.1 Static AST Parsing\n"
                    "Builds on https://github.com/daniel72584/grafeando and Figure 1.\n"
                    "Table 1: Performance Comparison\n"
                ),
            ]

    monkeypatch.setattr("parsers.pdf_parser.pypdf.PdfReader", FakeReader)

    parser = PdfParser()
    res = parser.parse_file("2601.15153v1.pdf", b"%PDF-1.4")

    sections = {f["name"] for f in res["functions"] if f["category"] == "pdf_section"}
    assert {"Abstract", "1 Introduction", "2 Methodology", "2.1 Static AST Parsing"}.issubset(sections)

    figures = {f["name"] for f in res["functions"] if f["category"] == "pdf_figure"}
    assert "Figure 1" in figures

    tables = {f["name"] for f in res["functions"] if f["category"] == "pdf_table"}
    assert "Table 1" in tables

    refs = {f["name"] for f in res["functions"] if f["category"] == "pdf_reference"}
    assert "arXiv:2601.15153v1" in refs
    assert "github.com/daniel72584/grafeando" in refs

    call_pairs = {(c["caller_id"].split("::")[-1], c["callee_name"]) for c in res["calls"]}
    assert ("Abstract", "Figure 1") in call_pairs
    assert ("Abstract", "2 Methodology") in call_pairs
    assert ("1 Introduction", "Table 1") in call_pairs
    assert ("2 Methodology", "2.1 Static AST Parsing") in call_pairs
    assert ("2.1 Static AST Parsing", "Figure 1") in call_pairs
