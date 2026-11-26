import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from parser import CodeParser
from graph_engine import GraphEngine


def main() -> None:
    parser = CodeParser()
    parsed = parser.parse_directory(str(ROOT), relative_to_root=True)
    engine = GraphEngine(":memory:")
    engine.ingest_parse_data(parsed)
    graph_data = engine.export_graph_data()

    payload = {
        "project_name": "grafeando (demo)",
        "nodes": graph_data["nodes"],
        "edges": graph_data["edges"],
        "stats": graph_data["stats"],
    }

    out_path = ROOT / "docs" / "demo-graph.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(
        f"Generated {out_path} ({payload['stats']['files']} files, "
        f"{payload['stats']['nodes']} nodes, {payload['stats']['edges']} edges)"
    )


if __name__ == "__main__":
    main()
