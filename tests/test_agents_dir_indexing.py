import os
import tempfile
from parser import CodeParser


def test_parse_directory_includes_agents_folder():
    parser = CodeParser()
    with tempfile.TemporaryDirectory() as tmpdir:
        agents_dir = os.path.join(tmpdir, ".agents", "agents")
        os.makedirs(agents_dir, exist_ok=True)
        sample_agent_path = os.path.join(agents_dir, "supervisor.md")
        with open(sample_agent_path, "w", encoding="utf-8") as f:
            f.write("# Supervisor\n\nCoordinates [scanner](scanner.md).\n")

        hidden_dir = os.path.join(tmpdir, ".hidden")
        os.makedirs(hidden_dir, exist_ok=True)
        with open(os.path.join(hidden_dir, "secret.md"), "w", encoding="utf-8") as f:
            f.write("# Secret\n")

        res = parser.parse_directory(tmpdir)
        indexed_files = [f["path"] for f in res["files"]]

        assert any("supervisor.md" in p for p in indexed_files)
        assert not any("secret.md" in p for p in indexed_files)
