import os
import csv
import io
from typing import Dict, List, Any
from parsers.base import BaseParser


class CsvParser(BaseParser):
    def parse_file(self, file_path: str, code_bytes: bytes) -> Dict[str, List[Dict[str, Any]]]:
        res = self.empty_result()
        rel_path = os.path.relpath(file_path)
        res["files"].append({"id": rel_path, "path": rel_path, "language": "csv"})

        dataset_name = os.path.basename(file_path)
        dataset_id = f"{rel_path}::{dataset_name}"

        res["classes"].append({
            "id": dataset_id,
            "name": dataset_name,
            "file_path": rel_path,
            "category": "dataset"
        })

        try:
            text = code_bytes.decode("utf-8", errors="replace")
            reader = csv.reader(io.StringIO(text))
            headers = next(reader, None)
        except Exception as e:
            print(f"Error parsing CSV file {file_path}: {e}")
            return res

        if headers:
            for col in headers:
                col_name = col.strip()
                if not col_name:
                    continue

                col_id = f"{dataset_id}::{col_name}"
                res["classes"].append({
                    "id": col_id,
                    "name": col_name,
                    "file_path": rel_path,
                    "category": "csv_column"
                })

                # Check foreign key column linkage e.g. user_id -> users
                if col_name.endswith("_id") and len(col_name) > 3:
                    target_entity = col_name[:-3] + "s"  # e.g. user -> users
                    res["injects"].append({
                        "injector_id": dataset_id,
                        "target_class_name": target_entity
                    })
                    res["injects"].append({
                        "injector_id": dataset_id,
                        "target_class_name": col_name[:-3]
                    })

        return res
