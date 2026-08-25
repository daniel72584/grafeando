import os
import json
from typing import Dict, List, Any
import kuzu


class GraphEngine:
    def __init__(self, db_path: str = ""):
        """
        Initializes Kùzu graph database. If db_path is empty, defaults to .grafeando_db in working dir or GRAFEANDO_DB_PATH.
        """
        if not db_path:
            cwd = os.getcwd()
            if cwd == "/" or not os.access(cwd, os.W_OK):
                cwd = os.path.expanduser("~")
            db_path = os.environ.get("GRAFEANDO_DB_PATH", os.path.join(cwd, ".grafeando_db"))
        self.db_path = os.path.abspath(db_path)
        self._init_db()

    def _init_db(self):
        if self.db_path:
            db_dir = os.path.dirname(self.db_path)
            if db_dir and not os.path.exists(db_dir):
                try:
                    os.makedirs(db_dir, exist_ok=True)
                except Exception:
                    pass
            try:
                self.db = kuzu.Database(self.db_path)
            except Exception:
                self.db_path = ":memory:"
                self.db = kuzu.Database(":memory:")
        else:
            self.db = kuzu.Database(":memory:")
        self.conn = kuzu.Connection(self.db)
        self._create_schema()

    def _create_schema(self):
        # Create Node Tables
        tables_to_create = [
            "CREATE NODE TABLE File(id STRING, path STRING, language STRING, PRIMARY KEY (id));",
            "CREATE NODE TABLE Class(id STRING, name STRING, file_path STRING, category STRING, PRIMARY KEY (id));",
            "CREATE NODE TABLE Function(id STRING, name STRING, qualified_name STRING, file_path STRING, start_line INT64, category STRING, PRIMARY KEY (id));",
            "CREATE NODE TABLE Decorator(id STRING, name STRING, target_id STRING, file_path STRING, PRIMARY KEY (id));",
            "CREATE REL TABLE IMPORTS(FROM File TO File);",
            "CREATE REL TABLE CONTAINS(FROM Class TO Function);",
            "CREATE REL TABLE CALLS(FROM Function TO Function, FROM Function TO Class);",
            "CREATE REL TABLE INJECTS(FROM Class TO Class, FROM Function TO Function, FROM Function TO Class);",
            "CREATE REL TABLE RENDERS(FROM Function TO Function);",
            "CREATE REL TABLE IMPLEMENTS(FROM Class TO Class);",
            "CREATE REL TABLE DECORATED_WITH(FROM Function TO Decorator);",
            "CREATE REL TABLE CLASS_DECORATED_WITH(FROM Class TO Decorator);"
        ]
        for stmt in tables_to_create:
            try:
                self.conn.execute(stmt)
            except Exception:
                pass

    def reset_database(self, new_path: str = ""):
        """Re-initializes DB to clear existing nodes & edges."""
        if new_path:
            self.db_path = os.path.abspath(new_path)
        self._init_db()

    def ingest_parse_data(self, parse_data: Dict[str, List[Dict[str, Any]]]):
        """
        Ingests extracted files, classes, functions, calls, injects, renders, implements, and decorators into Kùzu.
        """
        # Build in-memory lookup maps for instant PK resolution
        func_map = {}
        for f in parse_data.get("functions", []):
            fid = str(f.get("id", "")).strip()
            if fid:
                func_map[f["name"]] = fid
                if "qualified_name" in f and f["qualified_name"]:
                    func_map[f["qualified_name"]] = fid

        class_map = {
            c["name"]: str(c["id"]).strip()
            for c in parse_data.get("classes", [])
            if str(c.get("id", "")).strip()
        }

        # Ingest Files
        for f in parse_data.get("files", []):
            fid = str(f.get("id", "")).strip()
            if not fid:
                continue
            try:
                self.conn.execute(
                    "MERGE (fl:File {id: $id}) ON CREATE SET fl.path = $path, fl.language = $language",
                    {"id": fid, "path": str(f.get("path", "")), "language": f.get("language", "unknown")}
                )
            except Exception as e:
                pass

        # Ingest Classes / Structs / Interfaces / Tables
        for cls in parse_data.get("classes", []):
            cid = str(cls.get("id", "")).strip()
            if not cid:
                continue
            try:
                self.conn.execute(
                    "MERGE (c:Class {id: $id}) ON CREATE SET c.name = $name, c.file_path = $file_path, c.category = $category",
                    {
                        "id": cid,
                        "name": cls.get("name", ""),
                        "file_path": cls.get("file_path", ""),
                        "category": cls.get("category", "class")
                    }
                )
            except Exception as e:
                pass

        # Ingest Functions / Methods / Hooks / Components / Endpoints / Procedures / Queries
        for func in parse_data.get("functions", []):
            fid = str(func.get("id", "")).strip()
            if not fid:
                continue
            try:
                self.conn.execute(
                    "MERGE (f:Function {id: $id}) ON CREATE SET f.name = $name, f.qualified_name = $qualified_name, f.file_path = $file_path, f.start_line = $start_line, f.category = $category",
                    {
                        "id": fid,
                        "name": func.get("name", ""),
                        "qualified_name": func.get("qualified_name", func.get("name", "")),
                        "file_path": func.get("file_path", ""),
                        "start_line": int(func.get("start_line", 1)),
                        "category": func.get("category", "function")
                    }
                )
            except Exception as e:
                pass

        # Ingest Decorators
        for dec in parse_data.get("decorators", []):
            did = str(dec.get("id", "")).strip()
            if not did:
                continue
            try:
                self.conn.execute(
                    "MERGE (d:Decorator {id: $id, name: $name, target_id: $target_id, file_path: $file_path})",
                    {
                        "id": did,
                        "name": dec.get("name", ""),
                        "target_id": dec.get("target_id", ""),
                        "file_path": dec.get("file_path", "")
                    }
                )
            except Exception as e:
                pass

        # Ingest CONTAINS (Class -> Function)
        for rel in parse_data.get("contains", []):
            cid = str(rel.get("class_id", "")).strip()
            fid = str(rel.get("function_id", "")).strip()
            if not cid or not fid:
                continue
            try:
                self.conn.execute(
                    "MATCH (c:Class {id: $class_id}), (f:Function {id: $function_id}) MERGE (c)-[:CONTAINS]->(f)",
                    {"class_id": cid, "function_id": fid}
                )
            except Exception:
                pass

        # Ingest CALLS (Function -> Function OR Function -> Class/Table) using direct PK lookups
        for call in parse_data.get("calls", []):
            caller_id = str(call.get("caller_id", "")).strip()
            callee_name = str(call.get("callee_name", "")).strip()
            if not caller_id or not callee_name:
                continue

            target_func_id = func_map.get(callee_name)
            target_class_id = class_map.get(callee_name)

            if target_func_id:
                try:
                    self.conn.execute(
                        "MATCH (caller:Function {id: $caller_id}), (callee:Function {id: $target_id}) MERGE (caller)-[:CALLS]->(callee)",
                        {"caller_id": caller_id, "target_id": target_func_id}
                    )
                except Exception:
                    pass
            elif target_class_id:
                try:
                    self.conn.execute(
                        "MATCH (caller:Function {id: $caller_id}), (callee:Class {id: $target_id}) MERGE (caller)-[:CALLS]->(callee)",
                        {"caller_id": caller_id, "target_id": target_class_id}
                    )
                except Exception:
                    pass

        # Ingest RENDERS (React Component -> Component)
        for ren in parse_data.get("renders", []):
            parent_id = str(ren.get("parent_func_id", "")).strip()
            rendered_comp = str(ren.get("rendered_component_name", "")).strip()
            if not parent_id or not rendered_comp:
                continue
            target_func_id = func_map.get(rendered_comp)
            if target_func_id:
                try:
                    self.conn.execute(
                        "MATCH (parent:Function {id: $parent_id}), (child:Function {id: $target_id}) MERGE (parent)-[:RENDERS]->(child)",
                        {"parent_id": parent_id, "target_id": target_func_id}
                    )
                except Exception:
                    pass

        # Ingest INJECTS (NestJS / FastAPI / Spring / Foreign Keys)
        for inj in parse_data.get("injects", []):
            inj_id = str(inj.get("injector_id", "")).strip()
            target_name = str(inj.get("target_class_name", "")).strip()
            if not inj_id or not target_name:
                continue

            target_class_id = class_map.get(target_name)
            target_func_id = func_map.get(target_name)

            if target_class_id:
                try:
                    self.conn.execute(
                        "MATCH (inj:Class {id: $inj_id}), (target:Class {id: $target_id}) MERGE (inj)-[:INJECTS]->(target)",
                        {"inj_id": inj_id, "target_id": target_class_id}
                    )
                except Exception:
                    pass
                try:
                    self.conn.execute(
                        "MATCH (inj:Function {id: $inj_id}), (target:Class {id: $target_id}) MERGE (inj)-[:INJECTS]->(target)",
                        {"inj_id": inj_id, "target_id": target_class_id}
                    )
                except Exception:
                    pass
            elif target_func_id:
                try:
                    self.conn.execute(
                        "MATCH (inj:Function {id: $inj_id}), (target:Function {id: $target_id}) MERGE (inj)-[:INJECTS]->(target)",
                        {"inj_id": inj_id, "target_id": target_func_id}
                    )
                except Exception:
                    pass

        # Ingest IMPLEMENTS (Class -> Interface Class)
        for imp in parse_data.get("implements", []):
            cid = str(imp.get("class_id", "")).strip()
            iface_name = str(imp.get("interface_name", "")).strip()
            if not cid or not iface_name:
                continue

            target_iface_id = class_map.get(iface_name)
            if target_iface_id:
                try:
                    self.conn.execute(
                        "MATCH (c:Class {id: $cid}), (iface:Class {id: $target_id}) MERGE (c)-[:IMPLEMENTS]->(iface)",
                        {"cid": cid, "target_id": target_iface_id}
                    )
                except Exception:
                    pass

    def get_blast_radius(self, function_name: str, depth: int = 3) -> List[Dict[str, Any]]:
        """
        Finds all functions/components/queries that directly or indirectly depend on function_name or table_name
        up to `depth` levels deep across CALLS and RENDERS relationships.
        """
        depth = max(1, min(depth, 10))
        results_list = []

        # 1. Query Function targets
        query_func = f"""
        MATCH (target:Function)<-[:CALLS|RENDERS*1..{depth}]-(caller:Function)
        WHERE target.name = $name OR target.id = $name OR target.qualified_name = $name
        RETURN DISTINCT caller.id AS id, caller.name AS name, caller.file_path AS file_path, caller.start_line AS start_line, caller.category AS category
        """
        try:
            res = self.conn.execute(query_func, {"name": function_name})
            while res.has_next():
                row = res.get_next()
                results_list.append({
                    "id": row[0],
                    "name": row[1],
                    "file_path": row[2],
                    "start_line": row[3],
                    "category": row[4]
                })
        except Exception:
            pass

        # 2. Query Class / Table targets called by Functions
        query_cls = f"""
        MATCH (target:Class)<-[:CALLS*1..{depth}]-(caller:Function)
        WHERE target.name = $name OR target.id = $name
        RETURN DISTINCT caller.id AS id, caller.name AS name, caller.file_path AS file_path, caller.start_line AS start_line, caller.category AS category
        """
        try:
            res = self.conn.execute(query_cls, {"name": function_name})
            while res.has_next():
                row = res.get_next()
                item = {
                    "id": row[0],
                    "name": row[1],
                    "file_path": row[2],
                    "start_line": row[3],
                    "category": row[4]
                }
                if item not in results_list:
                    results_list.append(item)
        except Exception:
            pass

        return results_list

    def get_injection_dependencies(self, class_name: str) -> List[Dict[str, Any]]:
        """
        Finds classes or functions (Controllers/Services/Tables/Packages) that inject or reference class_name.
        """
        results_list = []
        # Class -> Class / Table -> Table
        q1 = """
        MATCH (injector:Class)-[:INJECTS]->(target:Class)
        WHERE target.name = $name OR target.id = $name
        RETURN DISTINCT injector.id AS id, injector.name AS name, injector.file_path AS file_path, injector.category AS category
        """
        try:
            res = self.conn.execute(q1, {"name": class_name})
            while res.has_next():
                row = res.get_next()
                results_list.append({
                    "id": row[0],
                    "name": row[1],
                    "file_path": row[2],
                    "category": row[3]
                })
        except Exception:
            pass

        # Function -> Function (e.g. FastAPI Depends)
        q2 = """
        MATCH (injector:Function)-[:INJECTS]->(target:Function)
        WHERE target.name = $name OR target.id = $name
        RETURN DISTINCT injector.id AS id, injector.name AS name, injector.file_path AS file_path, injector.category AS category
        """
        try:
            res = self.conn.execute(q2, {"name": class_name})
            while res.has_next():
                row = res.get_next()
                item = {
                    "id": row[0],
                    "name": row[1],
                    "file_path": row[2],
                    "category": row[3]
                }
                if item not in results_list:
                    results_list.append(item)
        except Exception:
            pass

        return results_list

    def export_graph_html(self, output_file: str = "grafeando-graph.html") -> str:
        """
        Exports the entire graph database into a standalone interactive HTML visualizer
        with physics simulation, multi-select category filters, node limit selector (1k default),
        instant search, and node neighborhood / blast radius inspector.
        """
        nodes = []
        node_ids = set()

        # 1. Fetch Classes
        r = self.conn.execute("MATCH (c:Class) RETURN c.id, c.name, c.file_path, c.category")
        while r.has_next():
            row = r.get_next()
            nid = str(row[0])
            name = str(row[1])
            file_path = str(row[2])
            cat = str(row[3]) or "class"

            group = "class"
            lname = name.lower()
            lcat = cat.lower()
            if "controller" in lname or "controller" in lcat:
                group = "controller"
            elif "service" in lname or "service" in lcat:
                group = "service"
            elif "module" in lname or "module" in lcat:
                group = "module"
            elif "schema" in lname or "entity" in lname or "dto" in lname or "table" in lcat or "model" in lname:
                group = "schema"

            nodes.append({
                "id": nid,
                "label": name,
                "group": group,
                "category": cat,
                "file_path": file_path,
                "start_line": 1,
                "node_type": "Class",
                "shape": "box"
            })
            node_ids.add(nid)

        # 2. Fetch Functions
        r = self.conn.execute("MATCH (f:Function) RETURN f.id, f.name, f.qualified_name, f.file_path, f.start_line, f.category")
        while r.has_next():
            row = r.get_next()
            nid = str(row[0])
            name = str(row[1])
            qname = str(row[2])
            file_path = str(row[3])
            start_line = row[4]
            cat = str(row[5]) or "function"

            group = "function"
            if cat == "component" or "component" in cat.lower():
                group = "component"
            elif cat == "endpoint" or "endpoint" in cat.lower():
                group = "endpoint"
            elif cat == "method" or "method" in cat.lower():
                group = "method"

            nodes.append({
                "id": nid,
                "label": name,
                "group": group,
                "category": cat,
                "file_path": file_path,
                "start_line": start_line,
                "node_type": "Function",
                "qualified_name": qname,
                "shape": "ellipse" if group in ["function", "method"] else "box"
            })
            node_ids.add(nid)

        edges = []
        edge_set = set()
        node_degree = {nid: 0 for nid in node_ids}

        # CALLS
        r = self.conn.execute("MATCH (a)-[r:CALLS]->(b) RETURN a.id, b.id")
        while r.has_next():
            row = r.get_next()
            u, v = str(row[0]), str(row[1])
            if u in node_ids and v in node_ids:
                k = (u, v, "CALLS")
                if k not in edge_set:
                    edge_set.add(k)
                    edges.append({"from": u, "to": v, "type": "CALLS", "label": "calls", "arrows": "to"})
                    node_degree[u] = node_degree.get(u, 0) + 1
                    node_degree[v] = node_degree.get(v, 0) + 1

        # INJECTS
        r = self.conn.execute("MATCH (a)-[r:INJECTS]->(b) RETURN a.id, b.id")
        while r.has_next():
            row = r.get_next()
            u, v = str(row[0]), str(row[1])
            if u in node_ids and v in node_ids:
                k = (u, v, "INJECTS")
                if k not in edge_set:
                    edge_set.add(k)
                    edges.append({"from": u, "to": v, "type": "INJECTS", "label": "injects", "arrows": "to", "dashes": True})
                    node_degree[u] = node_degree.get(u, 0) + 2
                    node_degree[v] = node_degree.get(v, 0) + 2

        # CONTAINS
        r = self.conn.execute("MATCH (c:Class)-[r:CONTAINS]->(f:Function) RETURN c.id, f.id")
        while r.has_next():
            row = r.get_next()
            u, v = str(row[0]), str(row[1])
            if u in node_ids and v in node_ids:
                k = (u, v, "CONTAINS")
                if k not in edge_set:
                    edge_set.add(k)
                    edges.append({"from": u, "to": v, "type": "CONTAINS", "label": "contains", "arrows": "to"})
                    node_degree[u] = node_degree.get(u, 0) + 1
                    node_degree[v] = node_degree.get(v, 0) + 1

        for n in nodes:
            n["degree"] = node_degree.get(n["id"], 0)

        nodes.sort(key=lambda x: x["degree"], reverse=True)

        nodes_json = json.dumps(nodes)
        edges_json = json.dumps(edges)

        html_template = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Grafeando Graph Explorer</title>
  <script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;700&family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <style>
    :root {{
      --bg-primary: #090d16;
      --bg-secondary: #0f172a;
      --bg-glass: rgba(15, 23, 42, 0.88);
      --border-color: rgba(255, 255, 255, 0.09);
      --border-focus: rgba(56, 189, 248, 0.4);
      --text-primary: #f8fafc;
      --text-secondary: #94a3b8;
      --text-muted: #64748b;
      --accent-cyan: #38bdf8;
      --accent-purple: #a855f7;
      --accent-emerald: #10b981;
      --accent-amber: #f59e0b;
      --accent-rose: #f43f5e;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
      background: radial-gradient(circle at 50% 0%, #1e1b4b 0%, #090d16 60%);
      color: var(--text-primary);
      overflow: hidden;
      width: 100vw;
      height: 100vh;
      display: flex;
    }}
    #network-container {{
      flex: 1;
      height: 100vh;
      position: relative;
      background: radial-gradient(#1e293b 1px, transparent 1px);
      background-size: 32px 32px;
    }}
    .top-toolbar {{
      position: absolute;
      top: 16px;
      left: 16px;
      right: 16px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      z-index: 50;
      pointer-events: none;
      flex-wrap: wrap;
    }}
    .toolbar-card {{
      pointer-events: auto;
      background: var(--bg-glass);
      backdrop-filter: blur(16px);
      -webkit-backdrop-filter: blur(16px);
      border: 1px solid var(--border-color);
      border-radius: 14px;
      padding: 8px 14px;
      box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.5), 0 8px 10px -6px rgba(0, 0, 0, 0.4);
      display: flex;
      align-items: center;
      gap: 10px;
    }}
    .logo-badge {{
      display: flex;
      align-items: center;
      gap: 8px;
      font-weight: 800;
      font-size: 15px;
      color: #fff;
      letter-spacing: -0.3px;
    }}
    .logo-icon {{ font-size: 18px; color: var(--accent-cyan); }}
    .stats-pill {{
      font-size: 12px;
      font-weight: 600;
      color: var(--text-secondary);
      background: rgba(255, 255, 255, 0.05);
      padding: 5px 10px;
      border-radius: 8px;
      border: 1px solid var(--border-color);
      display: flex;
      align-items: center;
      gap: 6px;
    }}
    .stats-count {{ color: var(--accent-cyan); }}
    .limit-control {{
      display: flex;
      align-items: center;
      gap: 6px;
      font-size: 12px;
      color: var(--text-secondary);
      font-weight: 600;
    }}
    .limit-select {{
      background: rgba(255, 255, 255, 0.06);
      border: 1px solid var(--border-color);
      color: var(--text-primary);
      padding: 5px 10px;
      border-radius: 8px;
      font-size: 12px;
      font-weight: 600;
      font-family: inherit;
      outline: none;
      cursor: pointer;
      transition: all 0.2s;
    }}
    .limit-select:focus {{
      border-color: var(--accent-cyan);
      background: rgba(255, 255, 255, 0.1);
    }}
    .limit-select option {{
      background: var(--bg-secondary);
      color: var(--text-primary);
    }}
    .search-wrapper {{ position: relative; width: 260px; }}
    .search-input {{
      width: 100%;
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid var(--border-color);
      border-radius: 10px;
      padding: 7px 12px 7px 32px;
      font-size: 13px;
      color: var(--text-primary);
      font-family: inherit;
      outline: none;
      transition: all 0.2s ease;
    }}
    .search-input:focus {{
      background: rgba(255, 255, 255, 0.1);
      border-color: var(--accent-cyan);
      box-shadow: 0 0 0 3px rgba(56, 189, 248, 0.2);
    }}
    .search-icon {{
      position: absolute;
      left: 10px;
      top: 50%;
      transform: translateY(-50%);
      font-size: 12px;
      color: var(--text-muted);
    }}
    .autocomplete-list {{
      position: absolute;
      top: calc(100% + 6px);
      left: 0;
      right: 0;
      background: var(--bg-secondary);
      border: 1px solid var(--border-color);
      border-radius: 10px;
      max-height: 280px;
      overflow-y: auto;
      z-index: 100;
      display: none;
      box-shadow: 0 12px 28px rgba(0,0,0,0.6);
    }}
    .autocomplete-item {{
      padding: 8px 12px;
      font-size: 12px;
      cursor: pointer;
      display: flex;
      justify-content: space-between;
      align-items: center;
      border-bottom: 1px solid rgba(255,255,255,0.03);
    }}
    .autocomplete-item:hover {{
      background: rgba(56, 189, 248, 0.15);
      color: var(--accent-cyan);
    }}
    .btn {{
      background: rgba(255, 255, 255, 0.06);
      border: 1px solid var(--border-color);
      color: var(--text-primary);
      padding: 6px 12px;
      border-radius: 8px;
      font-size: 12px;
      font-weight: 600;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 6px;
      transition: all 0.2s;
      outline: none;
      font-family: inherit;
    }}
    .btn:hover {{
      background: rgba(255, 255, 255, 0.12);
      border-color: rgba(255, 255, 255, 0.2);
    }}
    .btn-active {{
      background: rgba(56, 189, 248, 0.2);
      border-color: var(--accent-cyan);
      color: var(--accent-cyan);
    }}
    .filter-panel {{
      position: absolute;
      bottom: 20px;
      left: 20px;
      background: var(--bg-glass);
      backdrop-filter: blur(16px);
      border: 1px solid var(--border-color);
      border-radius: 14px;
      padding: 10px 14px;
      display: flex;
      flex-direction: column;
      gap: 8px;
      z-index: 40;
      max-width: 65%;
      box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.5);
    }}
    .filter-header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: 11px;
      font-weight: 700;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }}
    .filter-actions {{ display: flex; gap: 8px; }}
    .filter-action-link {{
      color: var(--accent-cyan);
      cursor: pointer;
      text-transform: none;
      font-size: 11px;
      font-weight: 600;
      transition: opacity 0.15s;
    }}
    .filter-action-link:hover {{ text-decoration: underline; }}
    .filter-pills {{ display: flex; flex-wrap: wrap; gap: 6px; }}
    .pill {{
      background: rgba(255, 255, 255, 0.04);
      border: 1px solid var(--border-color);
      padding: 5px 10px;
      border-radius: 8px;
      font-size: 11px;
      font-weight: 600;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 6px;
      transition: all 0.15s;
      user-select: none;
      color: var(--text-muted);
    }}
    .pill:hover {{ background: rgba(255, 255, 255, 0.08); color: var(--text-primary); }}
    .pill.active {{
      color: var(--text-primary);
      border-color: rgba(255, 255, 255, 0.25);
      box-shadow: 0 0 10px rgba(0,0,0,0.3);
    }}
    .pill-checkbox {{
      width: 13px;
      height: 13px;
      border-radius: 3px;
      border: 1.5px solid var(--text-muted);
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 9px;
      color: #000;
      background: transparent;
      transition: all 0.15s;
    }}
    .pill.active .pill-checkbox {{ background: #fff; border-color: #fff; }}
    .dot {{ width: 7px; height: 7px; border-radius: 50%; }}
    .edge-toolbar {{ position: absolute; bottom: 20px; right: 20px; display: flex; gap: 8px; z-index: 40; }}
    .inspector-drawer {{
      position: absolute;
      top: 0;
      right: 0;
      bottom: 0;
      width: 380px;
      background: rgba(10, 15, 29, 0.95);
      backdrop-filter: blur(24px);
      border-left: 1px solid var(--border-color);
      box-shadow: -10px 0 30px rgba(0, 0, 0, 0.7);
      z-index: 80;
      transform: translateX(100%);
      transition: transform 0.3s cubic-bezier(0.16, 1, 0.3, 1);
      display: flex;
      flex-direction: column;
    }}
    .inspector-drawer.open {{ transform: translateX(0); }}
    .inspector-header {{
      padding: 20px;
      border-bottom: 1px solid var(--border-color);
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
    }}
    .inspector-title {{ font-size: 16px; font-weight: 700; word-break: break-all; color: #fff; }}
    .badge {{
      display: inline-block;
      margin-top: 6px;
      font-size: 10px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      padding: 3px 8px;
      border-radius: 6px;
    }}
    .close-btn {{
      background: none;
      border: none;
      color: var(--text-muted);
      font-size: 18px;
      cursor: pointer;
      padding: 4px;
      border-radius: 6px;
    }}
    .close-btn:hover {{ color: #fff; background: rgba(255,255,255,0.1); }}
    .inspector-body {{
      padding: 20px;
      overflow-y: auto;
      flex: 1;
      display: flex;
      flex-direction: column;
      gap: 18px;
    }}
    .meta-box {{
      background: rgba(255, 255, 255, 0.03);
      border: 1px solid var(--border-color);
      border-radius: 10px;
      padding: 12px;
      font-size: 12px;
      font-family: 'JetBrains Mono', monospace;
      color: var(--text-secondary);
      word-break: break-all;
    }}
    .meta-label {{
      font-size: 10px;
      font-weight: 700;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.5px;
      margin-bottom: 4px;
      font-family: 'Plus Jakarta Sans', sans-serif;
    }}
    .rel-section-title {{
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      color: var(--text-muted);
      margin-bottom: 8px;
      display: flex;
      justify-content: space-between;
    }}
    .rel-list {{ display: flex; flex-direction: column; gap: 6px; max-height: 180px; overflow-y: auto; }}
    .rel-item {{
      background: rgba(255, 255, 255, 0.04);
      border: 1px solid var(--border-color);
      padding: 8px 10px;
      border-radius: 8px;
      font-size: 12px;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: space-between;
      transition: all 0.15s;
    }}
    .rel-item:hover {{
      background: rgba(56, 189, 248, 0.12);
      border-color: rgba(56, 189, 248, 0.3);
      color: var(--accent-cyan);
    }}
    .rel-tag {{
      font-size: 9px;
      padding: 2px 6px;
      border-radius: 4px;
      background: rgba(255,255,255,0.08);
      color: var(--text-muted);
    }}
    .blast-radius-btn {{
      background: linear-gradient(135deg, #6366f1 0%, #a855f7 100%);
      color: #fff;
      border: none;
      padding: 10px;
      border-radius: 10px;
      font-weight: 700;
      font-size: 12px;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      margin-top: 4px;
      transition: opacity 0.2s;
    }}
    .blast-radius-btn:hover {{ opacity: 0.9; }}
  </style>
</head>
<body>
  <div id="network-container"></div>
  <div class="top-toolbar">
    <div class="toolbar-card">
      <div class="logo-badge">
        <span class="logo-icon">🕸️</span>
        <span>Grafeando Explorer</span>
      </div>
      <div class="stats-pill" id="stats-display">
        <span>Showing</span> <span class="stats-count" id="stat-visible-nodes">0</span> <span>/</span> <span id="stat-total-nodes">0</span> <span>nodes</span>
      </div>
    </div>
    <div class="toolbar-card">
      <div class="limit-control">
        <span>Max Nodes:</span>
        <select class="limit-select" id="limit-select">
          <option value="250">250 nodes</option>
          <option value="500">500 nodes</option>
          <option value="1000" selected>1,000 nodes (Default)</option>
          <option value="2500">2,500 nodes</option>
          <option value="5000">5,000 nodes</option>
          <option value="999999">All / Unlimited</option>
        </select>
      </div>
      <div class="search-wrapper">
        <span class="search-icon">🔍</span>
        <input type="text" class="search-input" id="search-input" placeholder="Search symbol or path..." autocomplete="off" />
        <div class="autocomplete-list" id="autocomplete-list"></div>
      </div>
      <button class="btn" id="btn-focus-mode" title="Highlight neighbors of selected node">🎯 Focus Neighbors</button>
      <button class="btn" id="btn-physics" title="Toggle force layout simulation">⚡ Physics</button>
      <button class="btn" id="btn-fit" title="Fit all nodes in view">🔍 Reset Zoom</button>
    </div>
  </div>
  <div class="filter-panel">
    <div class="filter-header">
      <span>Category Filters (Multi-Select)</span>
      <div class="filter-actions">
        <span class="filter-action-link" id="select-all-cats">Select All</span>
        <span style="color:var(--border-color)">|</span>
        <span class="filter-action-link" id="clear-all-cats">Clear All</span>
      </div>
    </div>
    <div class="filter-pills" id="filter-pills"></div>
  </div>
  <div class="edge-toolbar">
    <div class="toolbar-card">
      <button class="btn btn-active" id="toggle-calls" data-type="CALLS">📞 Calls</button>
      <button class="btn btn-active" id="toggle-injects" data-type="INJECTS">💉 Injects</button>
      <button class="btn btn-active" id="toggle-contains" data-type="CONTAINS">📦 Contains</button>
    </div>
  </div>
  <div class="inspector-drawer" id="inspector-drawer">
    <div class="inspector-header">
      <div>
        <div class="inspector-title" id="inspect-name">Node Name</div>
        <span class="badge" id="inspect-badge">CLASS</span>
      </div>
      <button class="close-btn" id="inspect-close">✕</button>
    </div>
    <div class="inspector-body">
      <div>
        <div class="meta-label">File Location</div>
        <div class="meta-box" id="inspect-file">src/example.ts:1</div>
      </div>
      <button class="blast-radius-btn" id="btn-calc-blast">
        <span>💥</span> Focus Blast Radius (3 Hops)
      </button>
      <div>
        <div class="rel-section-title">
          <span>Incoming Dependents (Callers / Injectors)</span>
          <span id="count-incoming" class="rel-tag">0</span>
        </div>
        <div class="rel-list" id="list-incoming"></div>
      </div>
      <div>
        <div class="rel-section-title">
          <span>Outgoing Dependencies (Callees / Injected)</span>
          <span id="count-outgoing" class="rel-tag">0</span>
        </div>
        <div class="rel-list" id="list-outgoing"></div>
      </div>
    </div>
  </div>
  <script>
    const rawNodes = {nodes_json};
    const rawEdges = {edges_json};

    const colorMap = {{
      controller: {{ bg: '#8b5cf6', border: '#a78bfa', text: '#ffffff' }},
      service:    {{ bg: '#0284c7', border: '#38bdf8', text: '#ffffff' }},
      module:     {{ bg: '#059669', border: '#34d399', text: '#ffffff' }},
      schema:     {{ bg: '#d97706', border: '#fbbf24', text: '#ffffff' }},
      class:      {{ bg: '#475569', border: '#94a3b8', text: '#ffffff' }},
      endpoint:   {{ bg: '#4f46e5', border: '#818cf8', text: '#ffffff' }},
      component:  {{ bg: '#db2777', border: '#f472b6', text: '#ffffff' }},
      method:     {{ bg: '#0f766e', border: '#2dd4bf', text: '#ffffff' }},
      function:   {{ bg: '#1e293b', border: '#64748b', text: '#cbd5e1' }}
    }};

    const allCategories = new Set();
    const groupCounts = {{}};
    rawNodes.forEach(n => {{
      allCategories.add(n.group);
      groupCounts[n.group] = (groupCounts[n.group] || 0) + 1;
    }});

    let selectedCategories = new Set(allCategories);
    let currentNodeLimit = 1000;
    const edgeTypes = {{ CALLS: true, INJECTS: true, CONTAINS: true }};

    const nodesDataSet = new vis.DataSet([]);
    const edgesDataSet = new vis.DataSet([]);

    const container = document.getElementById('network-container');
    const data = {{ nodes: nodesDataSet, edges: edgesDataSet }};

    const options = {{
      nodes: {{ scaling: {{ min: 10, max: 30 }} }},
      edges: {{ smooth: {{ enabled: true, type: 'dynamic' }} }},
      physics: {{
        enabled: true,
        solver: 'forceAtlas2Based',
        forceAtlas2Based: {{
          gravitationalConstant: -35,
          centralGravity: 0.005,
          springLength: 70,
          springConstant: 0.12,
          damping: 0.4
        }},
        stabilization: {{ iterations: 90, updateInterval: 25 }}
      }},
      interaction: {{ hover: true, tooltipDelay: 100, keyboard: true }}
    }};

    const network = new vis.Network(container, data, options);

    function applyFiltersAndRender(fit = false) {{
      const filteredByCategory = rawNodes.filter(n => selectedCategories.has(n.group));
      const limitedNodes = filteredByCategory.slice(0, currentNodeLimit);
      const visibleNodeIds = new Set(limitedNodes.map(n => n.id));

      const formattedNodes = limitedNodes.map(n => {{
        const c = colorMap[n.group] || colorMap.class;
        return {{
          id: n.id,
          label: n.label,
          shape: n.shape || 'box',
          color: {{
            background: c.bg,
            border: c.border,
            highlight: {{ background: c.border, border: '#ffffff' }},
            hover: {{ background: c.border, border: '#ffffff' }}
          }},
          font: {{ color: c.text, size: 12, face: 'Plus Jakarta Sans', strokeWidth: 0 }},
          margin: {{ top: 6, bottom: 6, left: 10, right: 10 }},
          borderWidth: 1.5,
          shadow: {{ enabled: true, color: 'rgba(0,0,0,0.3)', size: 4 }},
          meta: n
        }};
      }});

      const formattedEdges = [];
      rawEdges.forEach((e, idx) => {{
        if (edgeTypes[e.type] && visibleNodeIds.has(e.from) && visibleNodeIds.has(e.to)) {{
          let col = '#475569';
          let dashes = false;
          if (e.type === 'CALLS') col = '#38bdf8';
          if (e.type === 'INJECTS') {{ col = '#a855f7'; dashes = true; }}
          if (e.type === 'CONTAINS') col = '#334155';

          formattedEdges.push({{
            id: 'e_' + idx,
            from: e.from,
            to: e.to,
            arrows: 'to',
            dashes: dashes,
            color: {{ color: col, highlight: '#ffffff', opacity: 0.5 }},
            width: e.type === 'INJECTS' ? 2 : 1.2,
            smooth: {{ type: 'continuous' }},
            meta: e
          }});
        }}
      }});

      nodesDataSet.clear();
      nodesDataSet.add(formattedNodes);
      edgesDataSet.clear();
      edgesDataSet.add(formattedEdges);

      document.getElementById('stat-visible-nodes').innerText = formattedNodes.length.toLocaleString();
      document.getElementById('stat-total-nodes').innerText = rawNodes.length.toLocaleString();

      if (fit) {{
        network.fit({{ animation: {{ duration: 500, easingFunction: 'easeInOutQuad' }} }});
      }}
    }}

    const pillsContainer = document.getElementById('filter-pills');
    function renderCategoryPills() {{
      pillsContainer.innerHTML = '';
      const sortedCategories = Array.from(allCategories).sort((a,b) => (groupCounts[b] || 0) - (groupCounts[a] || 0));

      sortedCategories.forEach(cat => {{
        const isSelected = selectedCategories.has(cat);
        const c = colorMap[cat] || colorMap.class;
        const pill = document.createElement('div');
        pill.className = `pill ${{isSelected ? 'active' : ''}}`;
        if (isSelected) {{
          pill.style.background = 'rgba(255, 255, 255, 0.08)';
          pill.style.borderColor = c.border;
        }}

        pill.innerHTML = `
          <div class=\"pill-checkbox\">${{isSelected ? '✓' : ''}}</div>
          <div class=\"dot\" style=\"background:${{c.bg}}\"></div>
          <span>${{cat}}</span>
          <span style=\"opacity:0.6; font-size:10px;\">${{groupCounts[cat] || 0}}</span>
        `;

        pill.onclick = () => {{
          if (selectedCategories.has(cat)) {{
            if (selectedCategories.size > 1) {{
              selectedCategories.delete(cat);
            }}
          }} else {{
            selectedCategories.add(cat);
          }}
          renderCategoryPills();
          applyFiltersAndRender(false);
        }};

        pillsContainer.appendChild(pill);
      }});
    }}

    document.getElementById('select-all-cats').onclick = () => {{
      selectedCategories = new Set(allCategories);
      renderCategoryPills();
      applyFiltersAndRender(true);
    }};

    document.getElementById('clear-all-cats').onclick = () => {{
      selectedCategories = new Set(['controller', 'service']);
      renderCategoryPills();
      applyFiltersAndRender(true);
    }};

    document.getElementById('limit-select').addEventListener('change', (e) => {{
      currentNodeLimit = parseInt(e.target.value, 10) || 1000;
      applyFiltersAndRender(true);
    }});

    ['CALLS', 'INJECTS', 'CONTAINS'].forEach(type => {{
      const btn = document.getElementById(`toggle-${{type.toLowerCase()}}`);
      btn.onclick = () => {{
        edgeTypes[type] = !edgeTypes[type];
        btn.classList.toggle('btn-active', edgeTypes[type]);
        applyFiltersAndRender(false);
      }};
    }});

    let physicsEnabled = true;
    document.getElementById('btn-physics').onclick = () => {{
      physicsEnabled = !physicsEnabled;
      network.setOptions({{ physics: {{ enabled: physicsEnabled }} }});
      document.getElementById('btn-physics').classList.toggle('btn-active', physicsEnabled);
    }};

    document.getElementById('btn-fit').onclick = () => {{
      network.fit({{ animation: {{ duration: 600, easingFunction: 'easeInOutQuad' }} }});
    }};

    const searchInput = document.getElementById('search-input');
    const autoList = document.getElementById('autocomplete-list');

    searchInput.addEventListener('input', (e) => {{
      const val = e.target.value.toLowerCase().trim();
      if (!val) {{
        autoList.style.display = 'none';
        return;
      }}
      const matches = rawNodes.filter(n => n.label.toLowerCase().includes(val) || n.file_path.toLowerCase().includes(val)).slice(0, 15);
      if (matches.length === 0) {{
        autoList.style.display = 'none';
        return;
      }}
      autoList.innerHTML = matches.map(m => `
        <div class=\"autocomplete-item\" data-id=\"${{m.id}}\">
          <div>
            <strong>${{m.label}}</strong>
            <div style=\"font-size:10px; color:#64748b;\">${{m.file_path.split('/').slice(-2).join('/')}}</div>
          </div>
          <span class=\"badge\" style=\"background:${{colorMap[m.group]?.bg || '#475569'}}\">${{m.group}}</span>
        </div>
      `).join('');
      autoList.style.display = 'block';

      autoList.querySelectorAll('.autocomplete-item').forEach(item => {{
        item.onclick = () => {{
          const targetId = item.getAttribute('data-id');
          selectAndFocusNode(targetId, true);
          autoList.style.display = 'none';
          searchInput.value = '';
        }};
      }});
    }});

    document.addEventListener('click', (e) => {{
      if (!searchInput.contains(e.target) && !autoList.contains(e.target)) {{
        autoList.style.display = 'none';
      }}
    }});

    const drawer = document.getElementById('inspector-drawer');
    const inspectName = document.getElementById('inspect-name');
    const inspectBadge = document.getElementById('inspect-badge');
    const inspectFile = document.getElementById('inspect-file');
    const listIncoming = document.getElementById('list-incoming');
    const listOutgoing = document.getElementById('list-outgoing');
    const countIncoming = document.getElementById('count-incoming');
    const countOutgoing = document.getElementById('count-outgoing');
    let selectedNodeId = null;

    document.getElementById('inspect-close').onclick = () => {{
      drawer.classList.remove('open');
    }};

    window.selectAndFocusNode = function(nodeId, ensureVisible = false) {{
      selectedNodeId = nodeId;
      const nodeMeta = rawNodes.find(n => n.id === nodeId);
      if (!nodeMeta) return;

      if (ensureVisible && !nodesDataSet.get(nodeId)) {{
        if (!selectedCategories.has(nodeMeta.group)) {{
          selectedCategories.add(nodeMeta.group);
          renderCategoryPills();
        }}
        applyFiltersAndRender(false);
      }}

      network.selectNodes([nodeId]);
      network.focus(nodeId, {{ scale: 1.2, animation: {{ duration: 500, easingFunction: 'easeInOutQuad' }} }});

      inspectName.innerText = nodeMeta.label;
      const c = colorMap[nodeMeta.group] || colorMap.class;
      inspectBadge.innerText = nodeMeta.group.toUpperCase();
      inspectBadge.style.background = c.bg;
      inspectFile.innerText = `${{nodeMeta.file_path}}:${{nodeMeta.start_line || 1}}`;

      const incoming = rawEdges.filter(e => e.to === nodeId);
      const outgoing = rawEdges.filter(e => e.from === nodeId);

      countIncoming.innerText = incoming.length;
      countOutgoing.innerText = outgoing.length;

      listIncoming.innerHTML = incoming.map(e => {{
        const src = rawNodes.find(n => n.id === e.from);
        const name = src ? src.label : e.from;
        return `<div class=\"rel-item\" onclick=\"selectAndFocusNode('${{e.from}}', true)\">
          <span>${{name}}</span>
          <span class=\"rel-tag\">${{e.type}}</span>
        </div>`;
      }}).join('') || '<div style=\"font-size:11px; color:#64748b;\">No incoming connections</div>';

      listOutgoing.innerHTML = outgoing.map(e => {{
        const dst = rawNodes.find(n => n.id === e.to);
        const name = dst ? dst.label : e.to;
        return `<div class=\"rel-item\" onclick=\"selectAndFocusNode('${{e.to}}', true)\">
          <span>${{name}}</span>
          <span class=\"rel-tag\">${{e.type}}</span>
        </div>`;
      }}).join('') || '<div style=\"font-size:11px; color:#64748b;\">No outgoing connections</div>';

      drawer.classList.add('open');
    }};

    network.on('click', (params) => {{
      if (params.nodes.length > 0) {{
        selectAndFocusNode(params.nodes[0]);
      }}
    }});

    function isolateNeighborhood(centerId, depth = 3) {{
      const visitedNodes = new Set([centerId]);
      let currentLayer = new Set([centerId]);

      for (let i = 0; i < depth; i++) {{
        const nextLayer = new Set();
        rawEdges.forEach(e => {{
          if (currentLayer.has(e.from) && !visitedNodes.has(e.to)) {{
            visitedNodes.add(e.to);
            nextLayer.add(e.to);
          }}
          if (currentLayer.has(e.to) && !visitedNodes.has(e.from)) {{
            visitedNodes.add(e.from);
            nextLayer.add(e.from);
          }}
        }});
        currentLayer = nextLayer;
      }}

      const subNodesData = rawNodes.filter(n => visitedNodes.has(n.id)).map(n => {{
        const c = colorMap[n.group] || colorMap.class;
        return {{
          id: n.id,
          label: n.label,
          shape: n.shape || 'box',
          color: {{ background: c.bg, border: c.border }},
          font: {{ color: c.text, size: 12, face: 'Plus Jakarta Sans' }},
          meta: n
        }};
      }});

      const subEdgesData = [];
      rawEdges.forEach((e, idx) => {{
        if (visitedNodes.has(e.from) && visitedNodes.has(e.to)) {{
          let col = '#475569';
          let dashes = false;
          if (e.type === 'CALLS') col = '#38bdf8';
          if (e.type === 'INJECTS') {{ col = '#a855f7'; dashes = true; }}
          if (e.type === 'CONTAINS') col = '#334155';

          subEdgesData.push({{
            id: 'sub_e_' + idx,
            from: e.from,
            to: e.to,
            arrows: 'to',
            dashes: dashes,
            color: {{ color: col, opacity: 0.7 }},
            width: e.type === 'INJECTS' ? 2 : 1.2,
            meta: e
          }});
        }}
      }});

      nodesDataSet.clear();
      nodesDataSet.add(subNodesData);
      edgesDataSet.clear();
      edgesDataSet.add(subEdgesData);

      document.getElementById('stat-visible-nodes').innerText = subNodesData.length.toLocaleString();
      network.fit({{ animation: true }});
    }}

    document.getElementById('btn-focus-mode').onclick = () => {{
      if (selectedNodeId) {{
        isolateNeighborhood(selectedNodeId, 2);
      }} else {{
        alert('Please click on any node first to focus its neighborhood.');
      }}
    }};

    document.getElementById('btn-calc-blast').onclick = () => {{
      if (selectedNodeId) {{
        isolateNeighborhood(selectedNodeId, 3);
      }}
    }};

    renderCategoryPills();
    applyFiltersAndRender(true);
  </script>
</body>
</html>
"""
        abs_output = os.path.abspath(output_file)
        with open(abs_output, "w", encoding="utf-8") as f:
            f.write(html_template)

        return abs_output
