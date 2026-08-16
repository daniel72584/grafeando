import pytest
from parsers.markdown_parser import MarkdownParser


def test_parse_markdown_headings_and_links():
    parser = MarkdownParser()
    md_content = b"""
# Architecture Overview

This project uses [FastAPI](src/server.py) for the API.

## Database Design

See the [SQL Schema](schema.sql) for table definitions.
"""
    res = parser.parse_file("README.md", md_content)

    doc_names = [c["name"] for c in res["classes"] if c["category"] == "document"]
    assert "README.md" in doc_names

    sections = [f["name"] for f in res["functions"] if f["category"] == "section"]
    assert "Architecture Overview" in sections
    assert "Database Design" in sections

    called_files = [c["callee_name"] for c in res["calls"]]
    assert "server.py" in called_files
    assert "schema.sql" in called_files
