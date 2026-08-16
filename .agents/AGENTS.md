## grafeando

This project uses Grafeando graph context engine for AST dependency mapping, call graph analysis, and blast radius calculations.

Rules:
- Before modifying shared functions, classes, components, services, or database schemas, call `get_blast_radius(symbol_name, depth=3)` to assess downstream impact.
- For codebase, architecture, or relationship queries, run `index_codebase(".")` if not indexed, and query the graph instead of reading raw files or running blanket greps.
- Review blast radius results to inspect dependent callers and imports, ensuring zero breaking changes.
- After creating new modules, services, or exports, trigger `index_codebase(".")` to keep the AST context engine updated.
