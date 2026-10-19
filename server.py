import os
import sys
from pathlib import Path
from typing import Dict, Any

_pkg_root = str(Path(__file__).parent.resolve())
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    from mcp.server.mcpserver import MCPServer as FastMCP

try:
    from grafeando.parser import CodeParser
    from grafeando.graph_engine import GraphEngine
except ImportError:
    from parser import CodeParser
    from graph_engine import GraphEngine

# Initialize MCP Server
mcp = FastMCP("grafeando")

# Initialize Parser & Graph Database
code_parser = CodeParser()
_graph_db = None

def get_graph_db() -> GraphEngine:
    global _graph_db
    if _graph_db is None:
        cwd_db = os.path.abspath(".grafeando_db")
        if os.path.exists(cwd_db):
            _graph_db = GraphEngine(cwd_db)
        else:
            default_dir = os.path.expanduser("~")
            _graph_db = GraphEngine(os.path.join(default_dir, ".grafeando_db"))
    return _graph_db


import time
import subprocess
from typing import Dict, Any, Optional


def check_repo_sync_weekly(repo_path: str, interval_days: int = 7) -> Optional[str]:
    """
    Checks if 7+ days have elapsed since last sync verification.
    If so, performs a lightweight, non-blocking check against upstream remote.
    Returns a sync notice if the local repository is behind upstream.
    """
    git_dir = os.path.join(repo_path, ".git")
    if not os.path.exists(git_dir):
        return None

    stamp_file = os.path.join(git_dir, "grafeando_sync_check")
    now = time.time()
    if os.path.exists(stamp_file):
        try:
            with open(stamp_file, "r") as f:
                last_time = float(f.read().strip())
                if now - last_time < interval_days * 86400:
                    return None
        except Exception:
            pass

    try:
        # Non-blocking fetch with 3-second timeout
        subprocess.run(["git", "fetch", "--quiet"], cwd=repo_path, timeout=3, capture_output=True)

        upstream_ref = "@{u}"
        has_upstream = subprocess.run(
            ["git", "rev-parse", "--verify", "@{u}"],
            cwd=repo_path,
            timeout=2,
            capture_output=True
        ).returncode == 0

        if not has_upstream:
            for branch in ("origin/main", "origin/master"):
                if subprocess.run(
                    ["git", "rev-parse", "--verify", branch],
                    cwd=repo_path,
                    timeout=2,
                    capture_output=True
                ).returncode == 0:
                    upstream_ref = branch
                    has_upstream = True
                    break

        if has_upstream:
            res = subprocess.run(
                ["git", "rev-list", "--count", f"HEAD..{upstream_ref}"],
                cwd=repo_path,
                timeout=2,
                capture_output=True,
                text=True
            )
            if res.returncode == 0:
                behind_count = int(res.stdout.strip() or 0)
                try:
                    with open(stamp_file, "w") as f:
                        f.write(str(now))
                except Exception:
                    pass

                if behind_count > 0:
                    return (
                        f"💡 Weekly Sync Notice: Local branch is behind {upstream_ref} by {behind_count} commit(s). "
                        "Run 'git pull' or call 'check_repo_sync(auto_pull=True)' to stay updated."
                    )

        try:
            with open(stamp_file, "w") as f:
                f.write(str(now))
        except Exception:
            pass
    except Exception:
        pass

    return None


@mcp.tool()
def index_codebase(path: str = ".") -> str:
    """
    Parses source files in the given directory across supported languages:
    Python (.py), TypeScript/JavaScript (.ts, .tsx, .js, .jsx - NestJS & React),
    Go (.go), Java (.java), SQL (.sql), Markdown (.md), CSV (.csv), PDF (.pdf), and JSON (.json).
    Ingests extracted entities, call graphs, component render trees, and dependency injections into Kùzu.
    Automatically verifies weekly repository freshness against remote upstream.
    """
    abs_path = os.path.abspath(path)
    if not os.path.exists(abs_path):
        return f"Error: Path '{path}' does not exist."

    # Automatically resolve true project root if inside a nested subfolder
    root_path = code_parser.find_project_root(abs_path)

    db_path = os.path.join(root_path, ".grafeando_db")
    db = get_graph_db()
    db.reset_database(db_path)

    # Parse AST
    parsed_data = code_parser.parse_directory(root_path)

    # Ingest into Graph Database
    db.ingest_parse_data(parsed_data)

    num_files = len(parsed_data.get("files", []))
    num_classes = len(parsed_data.get("classes", []))
    num_functions = len(parsed_data.get("functions", []))
    num_calls = len(parsed_data.get("calls", []))
    num_renders = len(parsed_data.get("renders", []))
    num_injects = len(parsed_data.get("injects", []))

    sync_notice = check_repo_sync_weekly(root_path)

    msg = (
        f"Successfully indexed codebase at '{abs_path}'. "
        f"Ingested {num_files} files, {num_classes} classes/structs, {num_functions} functions/methods/components, "
        f"{num_calls} calls, {num_renders} React JSX renders, and {num_injects} DI injections into Kùzu graph."
    )
    if sync_notice:
        msg += f"\n\n{sync_notice}"

    return msg


@mcp.tool()
def check_repo_sync(path: str = ".", auto_pull: bool = False) -> Dict[str, Any]:
    """
    Verifies if the local repository is in sync with its upstream remote branch (origin/main).
    Optionally pulls changes (auto_pull=True) if working tree is clean.
    """
    abs_path = os.path.abspath(path)
    root_path = code_parser.find_project_root(abs_path)
    git_dir = os.path.join(root_path, ".git")

    if not os.path.exists(git_dir):
        return {
            "is_git_repo": False,
            "status": "Not a git repository.",
            "is_up_to_date": True
        }

    try:
        subprocess.run(["git", "fetch", "--quiet"], cwd=root_path, timeout=5, capture_output=True)

        upstream_ref = "@{u}"
        has_upstream = subprocess.run(
            ["git", "rev-parse", "--verify", "@{u}"],
            cwd=root_path,
            timeout=2,
            capture_output=True
        ).returncode == 0

        if not has_upstream:
            for branch in ("origin/main", "origin/master"):
                if subprocess.run(
                    ["git", "rev-parse", "--verify", branch],
                    cwd=root_path,
                    timeout=2,
                    capture_output=True
                ).returncode == 0:
                    upstream_ref = branch
                    has_upstream = True
                    break

        if not has_upstream:
            return {
                "is_git_repo": True,
                "status": "No remote upstream tracking branch detected.",
                "is_up_to_date": True
            }

        behind_res = subprocess.run(
            ["git", "rev-list", "--count", f"HEAD..{upstream_ref}"],
            cwd=root_path,
            timeout=2,
            capture_output=True,
            text=True
        )
        ahead_res = subprocess.run(
            ["git", "rev-list", "--count", f"{upstream_ref}..HEAD"],
            cwd=root_path,
            timeout=2,
            capture_output=True,
            text=True
        )

        behind_count = int(behind_res.stdout.strip() or 0) if behind_res.returncode == 0 else 0
        ahead_count = int(ahead_res.stdout.strip() or 0) if ahead_res.returncode == 0 else 0

        pull_executed = False
        pull_message = ""

        if auto_pull and behind_count > 0:
            status_res = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=root_path,
                timeout=2,
                capture_output=True,
                text=True
            )
            if status_res.stdout.strip():
                pull_message = "Cannot auto-pull: working tree has uncommitted changes. Please commit or stash first."
            else:
                pull_proc = subprocess.run(
                    ["git", "pull"],
                    cwd=root_path,
                    timeout=10,
                    capture_output=True,
                    text=True
                )
                pull_executed = pull_proc.returncode == 0
                pull_message = pull_proc.stdout.strip() if pull_executed else pull_proc.stderr.strip()
                if pull_executed:
                    behind_count = 0

        return {
            "is_git_repo": True,
            "upstream": upstream_ref,
            "behind_commits": behind_count,
            "ahead_commits": ahead_count,
            "is_up_to_date": behind_count == 0,
            "auto_pulled": pull_executed,
            "message": pull_message or ("Repository is up to date." if behind_count == 0 else f"Behind by {behind_count} commit(s).")
        }

    except Exception as e:
        return {
            "is_git_repo": True,
            "error": str(e),
            "is_up_to_date": False
        }


@mcp.tool()
def get_blast_radius(symbol_name: str, depth: int = 3) -> Dict[str, Any]:
    """
    Calculates the blast radius of changing a function, component, or class.
    Traverses dependent callers, rendered React parent components, and injected NestJS/Spring services up to `depth` levels deep.
    """
    db = get_graph_db()
    cwd_db = os.path.abspath(".grafeando_db")
    if os.path.exists(cwd_db) and os.path.abspath(db.db_path) != cwd_db:
        db.reset_database(cwd_db)

    callers = db.get_blast_radius(function_name=symbol_name, depth=depth)
    injections = db.get_injection_dependencies(class_name=symbol_name)

    return {
        "target_symbol": symbol_name,
        "depth": depth,
        "impacted_callers_count": len(callers),
        "impacted_callers": callers,
        "dependent_injections_count": len(injections),
        "dependent_injections": injections
    }


@mcp.tool()
def export_graph_html(output_file: str = "grafeando-graph.html") -> str:
    """
    Exports the indexed AST code graph into a standalone interactive HTML visualizer
    with physics simulation, multi-select category filters, node limit controls (1k default),
    instant search, and node neighborhood / blast radius inspector.
    """
    db = get_graph_db()
    cwd_db = os.path.abspath(".grafeando_db")
    if os.path.exists(cwd_db) and os.path.abspath(db.db_path) != cwd_db:
        db.reset_database(cwd_db)

    out_path = db.export_graph_html(output_file)
    return f"Successfully generated interactive HTML graph explorer at: {out_path}"


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

