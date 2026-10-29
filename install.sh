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

# 2. Check Python version & Virtual Environment
PYTHON_VERSION=$($PYTHON_CMD -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
if [ -n "$VIRTUAL_ENV" ]; then
    echo "✓ Found Python $PYTHON_VERSION (Active virtualenv: $VIRTUAL_ENV)"
else
    echo "✓ Found Python $PYTHON_VERSION"
    echo "💡 Tip: Creating a virtual environment (python3 -m venv venv && source venv/bin/activate) is recommended before installing."
fi

# 3. Install/Upgrade ladybug & grafeando via pip
echo "📦 Installing LadybugDB & grafeando package from GitHub..."
$PYTHON_CMD -m pip install --quiet --upgrade "ladybug>=0.22.0" git+https://github.com/daniel72584/grafeando.git

# 4. Run grafeando install/migrate for project workspace & global IDEs
if command -v grafeando >/dev/null 2>&1; then
    GRAFEANDO_BIN="grafeando"
else
    GRAFEANDO_BIN="$PYTHON_CMD -m grafeando"
fi

echo "🚀 Configuring MCP server for detected AI IDEs (Antigravity, Gemini, Claude, Cursor, Windsurf, Continue, Codex)..."
$GRAFEANDO_BIN install --project --platform auto

# If legacy .grafeando_db exists, trigger migration to refresh DB schema under LadybugDB
if [ -f ".grafeando_db" ] || [ -d ".grafeando_db" ]; then
    echo "🔄 Refreshing workspace database with LadybugDB engine..."
    $GRAFEANDO_BIN migrate --project --platform auto
else
    echo "⚡ Indexing workspace codebase graph..."
    $GRAFEANDO_BIN index .
fi

echo ""
echo "✨ Grafeando (powered by LadybugDB) successfully installed and ready!"
echo "AI Assistant MCP tools active: index_codebase, get_blast_radius, export_graph_html"
