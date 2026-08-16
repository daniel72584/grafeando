import os
from typing import Dict, Any

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    from mcp.server.mcpserver import MCPServer as FastMCP

from parser import CodeParser
from graph_engine import GraphEngine

# Initialize MCP Server
mcp = FastMCP("CodeContextEngine")

# Initialize Parser & Graph Database
code_parser = CodeParser()
graph_db = GraphEngine()


@mcp.tool()
def index_codebase(path: str = ".") -> str:
    """
    Parses source files in the given directory across supported languages:
    Python (.py), TypeScript/JavaScript (.ts, .tsx, .js, .jsx - NestJS & React),
    Go (.go), and Java (.java).
    Ingests extracted entities, call graphs, component render trees, and dependency injections into Kùzu.
    """
    abs_path = os.path.abspath(path)
    if not os.path.exists(abs_path):
        return f"Error: Path '{path}' does not exist."

    # Parse AST
    parsed_data = code_parser.parse_directory(abs_path)

    # Ingest into Graph Database
    graph_db.reset_database()
    graph_db.ingest_parse_data(parsed_data)

    num_files = len(parsed_data.get("files", []))
    num_classes = len(parsed_data.get("classes", []))
    num_functions = len(parsed_data.get("functions", []))
    num_calls = len(parsed_data.get("calls", []))
    num_renders = len(parsed_data.get("renders", []))
    num_injects = len(parsed_data.get("injects", []))

    return (
        f"Successfully indexed codebase at '{abs_path}'. "
        f"Ingested {num_files} files, {num_classes} classes/structs, {num_functions} functions/methods/components, "
        f"{num_calls} calls, {num_renders} React JSX renders, and {num_injects} DI injections into Kùzu graph."
    )


@mcp.tool()
def get_blast_radius(symbol_name: str, depth: int = 3) -> Dict[str, Any]:
    """
    Calculates the blast radius of changing a function, component, or class.
    Traverses dependent callers, rendered React parent components, and injected NestJS/Spring services up to `depth` levels deep.
    """
    callers = graph_db.get_blast_radius(function_name=symbol_name, depth=depth)
    injections = graph_db.get_injection_dependencies(class_name=symbol_name)

    return {
        "target_symbol": symbol_name,
        "depth": depth,
        "impacted_callers_count": len(callers),
        "impacted_callers": callers,
        "dependent_injections_count": len(injections),
        "dependent_injections": injections
    }


if __name__ == "__main__":
    mcp.run(transport="stdio")
