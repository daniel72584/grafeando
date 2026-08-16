import pytest
from parsers.json_parser import JsonParser


def test_parse_package_json():
    parser = JsonParser()
    code = b"""
{
  "name": "my-express-app",
  "dependencies": {
    "express": "^4.18.0",
    "cors": "^2.8.5"
  }
}
"""
    res = parser.parse_file("package.json", code)

    pkgs = [c["name"] for c in res["classes"] if c["category"] == "npm_dependency"]
    assert "express" in pkgs
    assert "cors" in pkgs

    inj_targets = [inj["target_class_name"] for inj in res["injects"]]
    assert "express" in inj_targets


def test_parse_openapi_json():
    parser = JsonParser()
    code = b"""
{
  "openapi": "3.0.0",
  "paths": {
    "/users": {
      "get": {
        "operationId": "getUsers"
      }
    }
  }
}
"""
    res = parser.parse_file("openapi.json", code)

    endpoints = [f["name"] for f in res["functions"]]
    assert "getUsers" in endpoints
