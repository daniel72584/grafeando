import io
import pytest
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
