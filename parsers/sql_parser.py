import os
import sqlglot
from sqlglot import exp
from typing import Dict, List, Any
from parsers.base import BaseParser


class SqlParser(BaseParser):
    def parse_file(self, file_path: str, code_bytes: bytes) -> Dict[str, List[Dict[str, Any]]]:
        res = self.empty_result()
        rel_path = os.path.relpath(file_path)
        res["files"].append({"id": rel_path, "path": rel_path, "language": "sql"})

        try:
            sql_text = code_bytes.decode("utf-8", errors="replace")
            statements = sqlglot.parse(sql_text)
        except Exception as e:
            print(f"Error parsing SQL file {file_path}: {e}")
            return res

        for idx, stmt in enumerate(statements):
            if not stmt:
                continue

            # 1. CREATE TABLE Statements
            if isinstance(stmt, exp.Create):
                kind = stmt.args.get("kind", "").upper()
                if "TABLE" in kind or isinstance(stmt.this, exp.Schema):
                    schema_expr = stmt.this
                    table_name = schema_expr.this.name if hasattr(schema_expr, "this") and hasattr(schema_expr.this, "name") else str(schema_expr)
                    table_id = f"{rel_path}::{table_name}"
                    res["classes"].append({
                        "id": table_id,
                        "name": table_name,
                        "file_path": rel_path,
                        "category": "table"
                    })

                    # Extract Foreign Key references
                    for fk in stmt.find_all(exp.Reference):
                        tbl_node = fk.find(exp.Table) or fk.find(exp.Identifier)
                        if tbl_node:
                            target_table = tbl_node.name if hasattr(tbl_node, "name") and tbl_node.name else str(tbl_node)
                            if target_table:
                                res["injects"].append({
                                    "injector_id": table_id,
                                    "target_class_name": target_table
                                })

                elif "FUNCTION" in kind or "PROCEDURE" in kind:
                    func_name = stmt.this.name if hasattr(stmt.this, "name") else str(stmt.this)
                    func_id = f"{rel_path}::{func_name}"
                    res["functions"].append({
                        "id": func_id,
                        "name": func_name,
                        "qualified_name": func_name,
                        "file_path": rel_path,
                        "start_line": idx + 1,
                        "end_line": idx + 1,
                        "category": "procedure"
                    })

            # 2. DML Queries (SELECT, INSERT, UPDATE, DELETE)
            elif isinstance(stmt, (exp.Select, exp.Insert, exp.Update, exp.Delete)):
                query_name = f"Query_{stmt.key.upper()}_L{idx+1}"
                query_id = f"{rel_path}::{query_name}"

                res["functions"].append({
                    "id": query_id,
                    "name": query_name,
                    "qualified_name": f"{rel_path}::{query_name}",
                    "file_path": rel_path,
                    "start_line": idx + 1,
                    "end_line": idx + 1,
                    "category": "query"
                })

                for tbl in stmt.find_all(exp.Table):
                    tbl_name = tbl.name
                    if tbl_name:
                        res["calls"].append({
                            "caller_id": query_id,
                            "callee_name": tbl_name
                        })

        return res
