from setuptools import setup, find_packages

setup(
    name="grafeando",
    version="1.0.0",
    description="Local Multi-Language Code Context Engine MCP Server for Blast Radius Analysis & Token Savings",
    author="Grafeando Team",
    packages=find_packages(),
    py_modules=["server", "parser", "graph_engine", "cli"],
    install_requires=[
        "mcp>=1.0.0",
        "kuzu>=0.4.0",
        "tree-sitter>=0.22.0",
        "tree-sitter-python>=0.21.0",
        "tree-sitter-typescript>=0.23.0",
        "tree-sitter-javascript>=0.25.0",
        "tree-sitter-go>=0.25.0",
        "tree-sitter-java>=0.23.0",
        "sqlglot>=30.0.0",
        "pypdf>=5.0.0"
    ],
    entry_points={
        "console_scripts": [
            "grafeando = cli:main",
        ],
    },
    python_requires=">=3.9",
)
