import os
import time
import json
from parser import CodeParser
from graph_engine import GraphEngine


def estimate_tokens(text: str) -> int:
    """Estimates token count (approx. 4 characters per token)."""
    return len(text) // 4


def run_benchmark(target_dir: str = "."):
    print("=" * 70)
    print(f"  MULTI-LANGUAGE CODE CONTEXT ENGINE BENCHMARK: {os.path.abspath(target_dir)}")
    print("=" * 70)

    # 1. Measure File Reading & Baseline Context Size
    start_file_read = time.perf_counter()
    total_code_chars = 0
    file_count = 0
    all_file_contents = []
    supported_extensions = {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".java", ".json", ".sql", ".md", ".csv", ".pdf"}

    for root, dirs, files in os.walk(target_dir):
        dirs[:] = [
            d for d in dirs
            if not d.startswith(".") and d not in (
                "venv", "env", "__pycache__", "build", "dist",
                "node_modules", ".next", "target", "vendor", ".agents"
            )
        ]
        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if ext in supported_extensions:
                file_count += 1
                full_path = os.path.join(root, file)
                try:
                    with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read()
                        total_code_chars += len(content)
                        all_file_contents.append(content)
                except Exception:
                    pass

    baseline_raw_tokens = estimate_tokens("\n".join(all_file_contents))

    # 2. Measure AST Parsing Performance
    parser = CodeParser()
    start_parse = time.perf_counter()
    parsed_data = parser.parse_directory(target_dir)
    parse_time_ms = (time.perf_counter() - start_parse) * 1000

    num_files = len(parsed_data["files"])
    num_classes = len(parsed_data["classes"])
    num_functions = len(parsed_data["functions"])
    num_calls = len(parsed_data["calls"])
    num_renders = len(parsed_data["renders"])
    num_injects = len(parsed_data["injects"])

    # 3. Measure Kùzu Ingestion Performance
    ge = GraphEngine()
    start_ingest = time.perf_counter()
    ge.ingest_parse_data(parsed_data)
    ingest_time_ms = (time.perf_counter() - start_ingest) * 1000

    # 4. Measure Query Latency & Token Reduction for Multi-Language Targets
    targets_to_test = [
        ("get_blast_radius", "Python Function"),
        ("UserService", "NestJS Service"),
        ("UserCard", "React Component"),
        ("ExecuteQuery", "Go Method"),
        ("findData", "Java Method")
    ]

    query_benchmarks = []

    for target_name, target_type in targets_to_test:
        start_query = time.perf_counter()
        callers = ge.get_blast_radius(target_name, depth=3)
        injections = ge.get_injection_dependencies(target_name)
        query_time_ms = (time.perf_counter() - start_query) * 1000

        result_payload = json.dumps({
            "target": target_name,
            "callers": callers,
            "injections": injections
        })
        mcp_payload_tokens = estimate_tokens(result_payload)

        token_savings_pct = (
            ((baseline_raw_tokens - mcp_payload_tokens) / baseline_raw_tokens * 100)
            if baseline_raw_tokens > 0 else 0
        )

        query_benchmarks.append({
            "target": target_name,
            "type": target_type,
            "query_time_ms": round(query_time_ms, 3),
            "dependents_found": len(callers) + len(injections),
            "mcp_tokens": mcp_payload_tokens,
            "token_reduction_pct": round(token_savings_pct, 2)
        })

    # Print Summary Metrics
    print(f"\n📊 CODEBASE METRICS:")
    print(f"  • Files Scanned:         {file_count}")
    print(f"  • Entities Ingested:     {num_classes} classes/structs | {num_functions} functions/components")
    print(f"  • Graph Edges:           {num_calls} calls | {num_renders} renders | {num_injects} DI injections")
    print(f"  • Full Codebase Tokens:  ~{baseline_raw_tokens:,} tokens")

    print(f"\n⚡ SPEED METRICS:")
    print(f"  • Multi-AST Parse Time:  {parse_time_ms:.2f} ms")
    print(f"  • Kùzu Ingestion Time:   {ingest_time_ms:.2f} ms")
    print(f"  • Total Indexing Time:   {(parse_time_ms + ingest_time_ms):.2f} ms")

    print(f"\n💰 TOKEN SAVINGS & QUERY LATENCY BENCHMARK:")
    print(f"  {'Target Symbol':<18} | {'Type':<16} | {'Latency':<9} | {'Impacted':<8} | {'MCP Tokens':<10} | {'Token Reduction':<15}")
    print("  " + "-" * 88)
    for qb in query_benchmarks:
        print(
            f"  {qb['target']:<18} | {qb['type']:<16} | {qb['query_time_ms']:>5.2f} ms | "
            f"{qb['dependents_found']:>8} | {qb['mcp_tokens']:>10} | {qb['token_reduction_pct']:>13.2f}%"
        )
    print("=" * 70)


if __name__ == "__main__":
    run_benchmark(".")
