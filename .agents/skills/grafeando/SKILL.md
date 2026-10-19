---
name: grafeando
description: Local multi-language graph context engine for blast radius analysis, call graph queries, and token reduction across Python, NestJS, React, Go, Java, JSON, SQL, MD, CSV, PDF.
---

# Grafeando Code Context Skill

Use `grafeando` to query code change blast radius and dependency relationships before editing files.

## Available MCP Tools
- `index_codebase(path)`: Indexes source code, AST entities, call graphs, React components, and dependency injections into Kùzu graph DB. Automatically verifies weekly repository freshness against remote upstream.
- `get_blast_radius(symbol_name, depth=3)`: Calculates impact radius for functions, components, services, or SQL tables.
- `check_repo_sync(path, auto_pull=False)`: Verifies git sync status against upstream remote, with optional auto-pull if working tree is clean.
