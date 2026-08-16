import pytest
from parsers.sql_parser import SqlParser


def test_parse_sql_ddl_and_dml():
    parser = SqlParser()
    code = b"""
CREATE TABLE users (
    id INT PRIMARY KEY,
    name VARCHAR(100)
);

CREATE TABLE orders (
    id INT PRIMARY KEY,
    user_id INT REFERENCES users(id),
    amount DECIMAL(10, 2)
);

SELECT o.id, u.name FROM orders o JOIN users u ON o.user_id = u.id;
"""
    res = parser.parse_file("schema.sql", code)

    tables = [c["name"] for c in res["classes"] if c["category"] == "table"]
    assert "users" in tables
    assert "orders" in tables

    # Check foreign key injection reference
    fk_targets = [inj["target_class_name"] for inj in res["injects"]]
    assert "users" in fk_targets

    # Check query calls
    called_tables = [c["callee_name"] for c in res["calls"]]
    assert "orders" in called_tables
    assert "users" in called_tables
