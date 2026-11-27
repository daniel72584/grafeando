from parsers.markdown_parser import MarkdownParser


def test_parse_markdown_headings_and_links():
    parser = MarkdownParser()
    md_content = b"""
# Architecture Overview

This project uses [FastAPI](src/server.py) for the API.
See [Database Design](#database-design) and [[Deployment Guide]].

```python
# Not a heading inside a code block
```

## Database Design

See the [SQL Schema](schema.sql) for table definitions.
"""
    res = parser.parse_file("README.md", md_content)

    doc_names = [c["name"] for c in res["classes"] if c["category"] == "document"]
    assert "README.md" in doc_names

    sections = {f["name"]: f for f in res["functions"] if f["category"] == "section"}
    assert "Architecture Overview" in sections
    assert "Database Design" in sections
    assert "Not a heading inside a code block" not in sections
    assert sections["Architecture Overview"]["start_line"] < sections["Database Design"]["start_line"]

    called_pairs = {(c["caller_id"].split("::")[-1], c["callee_name"]) for c in res["calls"]}
    assert ("H1_Architecture Overview", "Database Design") in called_pairs
    assert ("H1_Architecture Overview", "server.py") in called_pairs
    assert ("H1_Architecture Overview", "Deployment Guide") in called_pairs
    assert ("H2_Database Design", "schema.sql") in called_pairs
