import os
import sys
import json
import argparse
from pathlib import Path


def get_server_path() -> str:
    current_dir = Path(__file__).parent.resolve()
    return str(current_dir / "server.py")


def get_python_path() -> str:
    venv_py = Path(__file__).parent.resolve() / "venv" / "bin" / "python"
    if venv_py.exists():
        return str(venv_py)
    return sys.executable


def install_mcp_config(platform: str, project_scoped: bool = False):
    python_bin = get_python_path()
    server_script = get_server_path()

    mcp_entry = {
        "command": python_bin,
        "args": [server_script]
    }

    home = Path.home()
    cwd = Path.cwd()

    configs_to_update = []

    if platform in ("all", "claude"):
        if project_scoped:
            configs_to_update.append(cwd / ".claude" / "mcp.json")
        else:
            if sys.platform == "darwin":
                configs_to_update.append(home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json")
            elif sys.platform == "win32":
                appdata = os.environ.get("APPDATA", str(home / "AppData" / "Roaming"))
                configs_to_update.append(Path(appdata) / "Claude" / "claude_desktop_config.json")
            else:
                configs_to_update.append(home / ".config" / "Claude" / "claude_desktop_config.json")

    if platform in ("all", "cursor"):
        if project_scoped:
            configs_to_update.append(cwd / ".cursor" / "mcp.json")
        else:
            configs_to_update.append(home / ".cursor" / "mcp.json")

    if platform in ("all", "gemini"):
        if project_scoped:
            configs_to_update.append(cwd / ".gemini" / "mcp.json")
        else:
            configs_to_update.append(home / ".gemini" / "antigravity-ide" / "mcp.json")

    if platform in ("all", "windsurf"):
        if project_scoped:
            configs_to_update.append(cwd / ".windsurf" / "mcp.json")
        else:
            configs_to_update.append(home / ".codeium" / "windsurf" / "mcp_config.json")

    if platform in ("all", "continue"):
        if project_scoped:
            configs_to_update.append(cwd / ".continue" / "config.json")
        else:
            configs_to_update.append(home / ".continue" / "config.json")

    if platform in ("all", "codex"):
        if project_scoped:
            configs_to_update.append(cwd / ".codex" / "mcp.json")
        else:
            configs_to_update.append(home / ".codex" / "mcp.json")

    for config_path in configs_to_update:
        try:
            config_path.parent.mkdir(parents=True, exist_ok=True)
            data = {}
            if config_path.exists():
                try:
                    with open(config_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                except Exception:
                    data = {}

            if "mcpServers" not in data or not isinstance(data["mcpServers"], dict):
                data["mcpServers"] = {}

            data["mcpServers"]["grafeando"] = mcp_entry

            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)

            scope_label = "Project" if project_scoped else "Global"
            print(f"✅ [{scope_label}] Installed grafeando MCP server config at: {config_path}")

        except Exception as e:
            print(f"⚠️ Could not update config at {config_path}: {e}")

    # Also install assistant SKILL.md and AGENTS.md rule if project or global directory exists
    agents_dir = (cwd / ".agents") if project_scoped else (home / ".gemini" / "config")
    skill_dir = agents_dir / "skills" / "grafeando"
    try:
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_file = skill_dir / "SKILL.md"
        with open(skill_file, "w", encoding="utf-8") as f:
            f.write(f"""---
name: grafeando
description: Local multi-language graph context engine for blast radius analysis, call graph queries, and token reduction across Python, NestJS, React, Go, Java, JSON, SQL, MD, CSV, PDF.
---

# Grafeando Code Context Skill

Use `grafeando` to query code change blast radius and dependency relationships before editing files.

## Available MCP Tools
- `index_codebase(path)`: Indexes source code, AST entities, call graphs, React components, and dependency injections into Kùzu graph DB.
- `get_blast_radius(symbol_name, depth=3)`: Calculates impact radius for functions, components, services, or SQL tables.
""")
        print(f"✅ Installed Assistant Skill at: {skill_file}")

        agents_file = agents_dir / "AGENTS.md"
        rule_content = """
## grafeando

This project uses Grafeando graph context engine for AST dependency mapping, call graph analysis, and blast radius calculations.

Rules:
- Before modifying shared functions, classes, components, services, or database schemas, call `get_blast_radius(symbol_name, depth=3)` to assess downstream impact.
- For codebase, architecture, or relationship queries, run `index_codebase(".")` if not indexed, and query the graph instead of reading raw files or running blanket greps.
- Review blast radius results to inspect dependent callers and imports, ensuring zero breaking changes.
- After creating new modules, services, or exports, trigger `index_codebase(".")` to keep the AST context engine updated.
"""
        existing_content = ""
        if agents_file.exists():
            with open(agents_file, "r", encoding="utf-8") as f:
                existing_content = f.read()

        if "## grafeando" not in existing_content:
            with open(agents_file, "a", encoding="utf-8") as f:
                f.write(rule_content)
            print(f"✅ Installed AGENTS.md rule at: {agents_file}")
    except Exception as e:
        print(f"⚠️ Could not write skill or rule file: {e}")

    # Install git post-commit auto-indexing hook if inside a git repository
    git_hooks_dir = cwd / ".git" / "hooks"
    if git_hooks_dir.exists():
        try:
            hook_file = git_hooks_dir / "post-commit"
            hook_script = f"""#!/bin/sh
# Grafeando automatic post-commit AST graph index update (AST-only, ~43ms, 0 API cost)
if command -v grafeando >/dev/null 2>&1; then
    grafeando index . >/dev/null 2>&1 &
elif [ -f "{python_bin}" ]; then
    "{python_bin}" "{server_script}" index . >/dev/null 2>&1 &
fi
"""
            with open(hook_file, "w", encoding="utf-8") as f:
                f.write(hook_script)
            os.chmod(hook_file, 0o755)
            print(f"✅ Installed Git post-commit auto-indexing hook at: {hook_file}")
        except Exception as e:
            print(f"⚠️ Could not install git post-commit hook: {e}")




def main():
    parser = argparse.ArgumentParser(
        prog="grafeando",
        description="Grafeando: Local Multi-Language Code Context & Graph Engine MCP Server"
    )
    subparsers = parser.add_subparsers(dest="command")

    # Install command
    install_parser = subparsers.add_parser("install", help="Install grafeando MCP server config into IDEs")
    install_parser.add_argument("--project", action="store_true", help="Force project-scoped installation in current workspace")
    install_parser.add_argument("--global", dest="global_only", action="store_true", help="Force global user home profile installation only")
    install_parser.add_argument(
        "--platform",
        choices=["all", "claude", "cursor", "gemini", "windsurf", "continue", "codex"],
        default="all",
        help="Target IDE platform (default: all)"
    )

    # Index command
    index_parser = subparsers.add_parser("index", help="Index codebase at given directory path")
    index_parser.add_argument("path", nargs="?", default=".", help="Directory path to index (default: current directory)")

    # Server command
    subparsers.add_parser("server", help="Run grafeando MCP server on stdio")

    args = parser.parse_args()

    if args.command == "install":
        cwd = Path.cwd()
        is_workspace = args.project or (not args.global_only and any((cwd / item).exists() for item in [".git", "package.json", "setup.py", "go.mod", "pom.xml", "Cargo.toml"]))

        if is_workspace:
            print(f"🚀 Installing Grafeando MCP Server into Project Workspace '{cwd.name}'...")
            install_mcp_config(platform=args.platform, project_scoped=True)

        if not args.project:
            print(f"🚀 Ensuring Global IDE Profile Configurations...")
            install_mcp_config(platform=args.platform, project_scoped=False)

        if is_workspace:
            print("\n⚡ Running initial AST indexing on workspace...")
            try:
                from server import index_codebase
                msg = index_codebase(str(cwd))
                print(f"✅ {msg}")
            except Exception as e:
                print(f"⚠️ Initial indexing warning: {e}")

        print("\n✨ Grafeando installation complete! Open your AI assistant IDE and ask questions or use get_blast_radius.")

    elif args.command == "index":
        from server import index_codebase
        msg = index_codebase(args.path)
        print(msg)

    elif args.command == "server":
        from server import mcp
        mcp.run(transport="stdio")

    else:
        parser.print_help()



if __name__ == "__main__":
    main()
