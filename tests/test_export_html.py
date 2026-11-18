from graph_engine import GraphEngine


def test_export_graph_html_300_random_limit_and_show_more(tmp_path):
    """Verify exported HTML defaults to 300 random nodes and includes Show More controls."""
    db = GraphEngine(str(tmp_path / "test_db"))
    functions = [
        {
            "name": f"fn_{i}",
            "qualified_name": f"mod.fn_{i}",
            "file_path": "mod.py",
            "start_line": i + 1,
            "end_line": i + 2,
            "category": "function",
        }
        for i in range(350)
    ]
    db.ingest_parse_data({
        "classes": [],
        "functions": functions,
        "calls": [],
        "injections": [],
        "contains": [],
    })

    out_file = tmp_path / "graph.html"
    result_path = db.export_graph_html(str(out_file))
    html = out_file.read_text(encoding="utf-8")

    assert result_path == str(out_file)
    assert '<option value="300" selected>300 nodes (Default)</option>' in html
    assert "const NODE_PAGE_STEP = 300;" in html
    assert "let currentNodeLimit = NODE_PAGE_STEP;" in html
    assert "shuffleArray(rawNodes);" in html
    assert 'id="btn-show-more"' in html
