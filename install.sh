#!/usr/bin/env bash
set -e

echo "🕸️ Installing Grafeando Code Context & AST Graph Engine..."

# 1. Determine Python executable
if command -v python3 >/dev/null 2>&1; then
    PYTHON_CMD="python3"
elif command -v python >/dev/null 2>&1; then
    PYTHON_CMD="python"
else
    echo "❌ Error: Python 3.9+ is required but not found on your system."
    exit 1
fi

# 2. Check Python version
PYTHON_VERSION=$($PYTHON_CMD -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
echo "✓ Found Python $PYTHON_VERSION"

# 3. Install grafeando via pip
echo "📦 Installing grafeando package from GitHub..."
$PYTHON_CMD -m pip install --quiet --upgrade git+https://github.com/daniel72584/grafeando.git

# 4. Run grafeando install for project workspace & global IDEs
if command -v grafeando >/dev/null 2>&1; then
    GRAFEANDO_BIN="grafeando"
else
    GRAFEANDO_BIN="$PYTHON_CMD -m grafeando"
fi

echo "🚀 Configuring MCP server for AI IDEs (Antigravity/Gemini, Claude, Cursor, Windsurf, Continue, Codex)..."
$GRAFEANDO_BIN install --project

echo "⚡ Indexing workspace codebase graph..."
$GRAFEANDO_BIN index .

echo ""
echo "✨ Grafeando successfully installed and ready!"
echo "AI Assistant MCP tools active: index_codebase, get_blast_radius"
