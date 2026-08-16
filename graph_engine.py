import os
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
                    "MERGE (fl:File {id: $id, path: $path, language: $language})",
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
                    "MERGE (c:Class {id: $id, name: $name, file_path: $file_path, category: $category})",
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
                    "MERGE (f:Function {id: $id, name: $name, qualified_name: $qualified_name, file_path: $file_path, start_line: $start_line, category: $category})",
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
