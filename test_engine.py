import json
from parser import CodeParser
from graph_engine import GraphEngine
from server import index_codebase, get_blast_radius


def main():
    print("==================================================")
    print(" 1. Testing CodeParser Multi-Language Extraction ")
    print("==================================================")
    parser = CodeParser()
    res = parser.parse_directory("tests_fixtures")
    print(f"Files scanned:      {len(res['files'])}")
    print(f"Classes/Tables:     {len(res['classes'])}")
    print(f"Functions/Endpoints:{len(res['functions'])}")
    print(f"Call edges:         {len(res['calls'])}")
    print(f"Render edges:       {len(res['renders'])}")
    print(f"DI Injections/FKs:  {len(res['injects'])}")
    print(f"Decorators:         {len(res['decorators'])}")

    print("\n==================================================")
    print(" 2. Ingesting Multi-Language Codebase into Kùzu   ")
    print("==================================================")
    ge = GraphEngine()
    ge.reset_database()
    ge.ingest_parse_data(res)

    print("\n--- FastAPI Depends Query (get_db) ---")
    fastapi_br = ge.get_blast_radius("get_db", depth=3)
    print(json.dumps(fastapi_br, indent=2))

    print("\n--- SQL Query Table Dependency (users) ---")
    sql_br = ge.get_blast_radius("users", depth=3)
    sql_fk = ge.get_injection_dependencies("users")
    print("Queries calling 'users':", json.dumps(sql_br, indent=2))
    print("Tables referencing 'users':", json.dumps(sql_fk, indent=2))

    print("\n--- JSON Package Dependency (express) ---")
    json_deps = ge.get_injection_dependencies("express")
    print(json.dumps(json_deps, indent=2))

    print("\n==================================================")
    print(" 3. Testing MCP Server tool: index_codebase (.)  ")
    print("==================================================")
    idx_msg = index_codebase(".")
    print(idx_msg)


if __name__ == "__main__":
    main()
