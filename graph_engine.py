from typing import Dict, List, Any
import kuzu


class GraphEngine:
    def __init__(self, db_path: str = ""):
        """
        Initializes Kùzu graph database. If db_path is empty, creates an in-memory database instance.
        """
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        if self.db_path:
            self.db = kuzu.Database(self.db_path)
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

    def reset_database(self):
        """Re-initializes DB to clear existing nodes & edges."""
        self._init_db()

    def ingest_parse_data(self, parse_data: Dict[str, List[Dict[str, Any]]]):
        """
        Ingests extracted files, classes, functions, calls, injects, renders, implements, and decorators into Kùzu.
        """
        # Ingest Files
        for f in parse_data.get("files", []):
            try:
                self.conn.execute(
                    "MERGE (fl:File {id: $id, path: $path, language: $language})",
                    {"id": f["id"], "path": f["path"], "language": f.get("language", "unknown")}
                )
            except Exception as e:
                print(f"Error inserting file {f['id']}: {e}")

        # Ingest Classes / Structs / Interfaces / Tables
        for cls in parse_data.get("classes", []):
            try:
                self.conn.execute(
                    "MERGE (c:Class {id: $id, name: $name, file_path: $file_path, category: $category})",
                    {
                        "id": cls["id"],
                        "name": cls["name"],
                        "file_path": cls["file_path"],
                        "category": cls.get("category", "class")
                    }
                )
            except Exception as e:
                print(f"Error inserting class {cls['id']}: {e}")

        # Ingest Functions / Methods / Hooks / Components / Endpoints / Procedures / Queries
        for func in parse_data.get("functions", []):
            try:
                self.conn.execute(
                    "MERGE (f:Function {id: $id, name: $name, qualified_name: $qualified_name, file_path: $file_path, start_line: $start_line, category: $category})",
                    {
                        "id": func["id"],
                        "name": func["name"],
                        "qualified_name": func.get("qualified_name", func["name"]),
                        "file_path": func["file_path"],
                        "start_line": int(func["start_line"]),
                        "category": func.get("category", "function")
                    }
                )
            except Exception as e:
                print(f"Error inserting function {func['id']}: {e}")

        # Ingest Decorators
        for dec in parse_data.get("decorators", []):
            try:
                self.conn.execute(
                    "MERGE (d:Decorator {id: $id, name: $name, target_id: $target_id, file_path: $file_path})",
                    {
                        "id": dec["id"],
                        "name": dec["name"],
                        "target_id": dec["target_id"],
                        "file_path": dec["file_path"]
                    }
                )
            except Exception as e:
                print(f"Error inserting decorator {dec['id']}: {e}")

        # Ingest CONTAINS (Class -> Function)
        for rel in parse_data.get("contains", []):
            try:
                self.conn.execute(
                    "MATCH (c:Class {id: $class_id}), (f:Function {id: $function_id}) MERGE (c)-[:CONTAINS]->(f)",
                    {"class_id": rel["class_id"], "function_id": rel["function_id"]}
                )
            except Exception as e:
                print(f"Error inserting CONTAINS rel {rel}: {e}")

        # Ingest CALLS (Function -> Function OR Function -> Class/Table)
        for call in parse_data.get("calls", []):
            try:
                self.conn.execute(
                    """
                    MATCH (caller:Function {id: $caller_id}), (callee:Function)
                    WHERE callee.name = $callee_name OR callee.id = $callee_name OR callee.qualified_name = $callee_name
                    MERGE (caller)-[:CALLS]->(callee)
                    """,
                    {"caller_id": call["caller_id"], "callee_name": call["callee_name"]}
                )
            except Exception:
                pass

            try:
                self.conn.execute(
                    """
                    MATCH (caller:Function {id: $caller_id}), (callee:Class)
                    WHERE callee.name = $callee_name OR callee.id = $callee_name
                    MERGE (caller)-[:CALLS]->(callee)
                    """,
                    {"caller_id": call["caller_id"], "callee_name": call["callee_name"]}
                )
            except Exception:
                pass

        # Ingest RENDERS (React Component -> Component)
        for ren in parse_data.get("renders", []):
            try:
                self.conn.execute(
                    """
                    MATCH (parent:Function {id: $parent_func_id}), (child:Function)
                    WHERE child.name = $rendered_component_name OR child.id = $rendered_component_name
                    MERGE (parent)-[:RENDERS]->(child)
                    """,
                    {
                        "parent_func_id": ren["parent_func_id"],
                        "rendered_component_name": ren["rendered_component_name"]
                    }
                )
            except Exception as e:
                print(f"Error inserting RENDERS rel {ren}: {e}")

        # Ingest INJECTS (NestJS / FastAPI / Spring / Foreign Keys)
        for inj in parse_data.get("injects", []):
            # Class -> Class
            try:
                self.conn.execute(
                    """
                    MATCH (inj:Class {id: $injector_id}), (target:Class)
                    WHERE target.name = $target_class_name OR target.id = $target_class_name
                    MERGE (inj)-[:INJECTS]->(target)
                    """,
                    {
                        "injector_id": inj["injector_id"],
                        "target_class_name": inj["target_class_name"]
                    }
                )
            except Exception:
                pass

            # Function -> Function (e.g. FastAPI Endpoint -> Dependency Function)
            try:
                self.conn.execute(
                    """
                    MATCH (inj:Function {id: $injector_id}), (target:Function)
                    WHERE target.name = $target_class_name OR target.id = $target_class_name
                    MERGE (inj)-[:INJECTS]->(target)
                    """,
                    {
                        "injector_id": inj["injector_id"],
                        "target_class_name": inj["target_class_name"]
                    }
                )
            except Exception:
                pass

            # Function -> Class
            try:
                self.conn.execute(
                    """
                    MATCH (inj:Function {id: $injector_id}), (target:Class)
                    WHERE target.name = $target_class_name OR target.id = $target_class_name
                    MERGE (inj)-[:INJECTS]->(target)
                    """,
                    {
                        "injector_id": inj["injector_id"],
                        "target_class_name": inj["target_class_name"]
                    }
                )
            except Exception:
                pass

        # Ingest IMPLEMENTS (Class -> Interface Class)
        for imp in parse_data.get("implements", []):
            try:
                self.conn.execute(
                    """
                    MATCH (c:Class {id: $class_id}), (iface:Class)
                    WHERE iface.name = $interface_name OR iface.id = $interface_name
                    MERGE (c)-[:IMPLEMENTS]->(iface)
                    """,
                    {
                        "class_id": imp["class_id"],
                        "interface_name": imp["interface_name"]
                    }
                )
            except Exception as e:
                print(f"Error inserting IMPLEMENTS rel {imp}: {e}")

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
