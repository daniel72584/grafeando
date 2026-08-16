import pytest
from parsers.csv_parser import CsvParser


def test_parse_csv_columns_and_linkage():
    parser = CsvParser()
    csv_content = b"""id,user_id,amount,created_at
1,101,99.99,2026-08-16
2,102,149.50,2026-08-16
"""
    res = parser.parse_file("orders.csv", csv_content)

    datasets = [c["name"] for c in res["classes"] if c["category"] == "dataset"]
    assert "orders.csv" in datasets

    columns = [c["name"] for c in res["classes"] if c["category"] == "csv_column"]
    assert "user_id" in columns
    assert "amount" in columns

    inj_targets = [inj["target_class_name"] for inj in res["injects"]]
    assert "users" in inj_targets
