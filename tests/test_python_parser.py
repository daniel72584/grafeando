import pytest
from parsers.python_parser import PythonParser


def test_parse_fastapi_and_python():
    parser = PythonParser()
    code = b"""
from fastapi import FastAPI, Depends

app = FastAPI()

def get_db():
    return "db"

@app.get("/items")
def read_items(db = Depends(get_db)):
    return db

class ItemService:
    def process(self):
        get_db()
"""
    res = parser.parse_file("app.py", code)

    func_names = [f["name"] for f in res["functions"]]
    assert "get_db" in func_names
    assert "read_items" in func_names
    assert "process" in func_names

    categories = {f["name"]: f["category"] for f in res["functions"]}
    assert categories["read_items"] == "endpoint"
    assert categories["get_db"] == "function"
    assert categories["process"] == "method"

    # Check FastAPI Depends injection
    inject_targets = [inj["target_class_name"] for inj in res["injects"]]
    assert "get_db" in inject_targets
