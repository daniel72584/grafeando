import os
import pytest
from parser import CodeParser
from graph_engine import GraphEngine


def test_real_fastapi_official_template():
    repo_path = "real_test_repos/fastapi-template/backend"
    if not os.path.exists(repo_path):
        pytest.skip(f"Repository path {repo_path} does not exist.")

    parser = CodeParser()
    data = parser.parse_directory(repo_path)

    assert len(data["files"]) > 10
    assert len(data["functions"]) > 50
    assert len(data["calls"]) > 100

    ge = GraphEngine()
    ge.ingest_parse_data(data)

    # Test blast radius of get_db or session in real FastAPI repo
    br = ge.get_blast_radius("get_db", depth=3)
    assert isinstance(br, list)


def test_real_nestjs_official_cats_app():
    repo_path = "real_test_repos/nestjs-repo/sample/01-cats-app"
    if not os.path.exists(repo_path):
        pytest.skip(f"Repository path {repo_path} does not exist.")

    parser = CodeParser()
    data = parser.parse_directory(repo_path)

    assert len(data["classes"]) > 5
    assert len(data["functions"]) > 5

    ge = GraphEngine()
    ge.ingest_parse_data(data)

    # Test Dependency Injection query for CatsService in real NestJS repo
    deps = ge.get_injection_dependencies("CatsService")
    assert len(deps) >= 1
    assert any("CatsController" in d["name"] for d in deps)
