# Grafeando 🕸️

> **A map of your codebase for your AI assistant.**

`grafeando` helps AI coding tools (like **Cursor**, **Claude**, **Windsurf**, **Antigravity**) understand how all your files and functions connect to each other.

---

## The Eternal Problem of Context

No matter how large an AI context window gets, it will never be enough. The more raw information we put into it, the more noise, confusion, and token costs we get, creating an endless loop.

A better solution is to give the AI a persistent source of truth where it can look up information (architecture, problems, code, statements) on demand. Instead of forcing the agent to scan and reload the entire workspace in every new session, we index it once so every session already knows how everything connects.

To make this memory lightweight, fast, and 100% local without relying on other tools, we use an **AST (Abstract Syntax Tree)**. We parse the repository into a relationship graph and expose it through an **MCP server**.

Now, when you give the agent a prompt like:
> *"In the login controller, add this validation and update `user.tsx`"*

The agent doesn't need to load dozens of files into its context window. It just queries the graph, traces the exact dependencies and callers needed, and edits your code safely.

## ❓ What problem does it solve?

When you ask an AI to edit your code:
- **Without Grafeando**: The AI guesses or reads random files, often breaking connected code without realizing it.
- **With Grafeando**: The AI sees a complete map of your project, knows **exactly what will break**, and edits code safely.

It also cuts AI token usage by **99.9%**, making AI responses **faster and much cheaper**.

---

## ⚡ Quickstart (1-Line Install)

> 💡 **Recommended Step 1**: Create and activate a Python Virtual Environment before installing to ensure zero package conflicts:
> ```bash
> python3 -m venv venv && source venv/bin/activate
> ```

Run this single command in your project workspace directory to install `grafeando`, auto-detect your active AI IDEs (**Antigravity**, **Gemini**, **Cursor**, **Claude**, **Windsurf**, **Continue**, **Codex**), and index your codebase graph:

```bash
curl -sSL https://raw.githubusercontent.com/daniel72584/grafeando/main/install.sh | bash
```

<details>
<summary>📦 <b>Manual Installation & Virtual Environment Setup</b></summary>

```bash
# 1. Create and activate Python virtual environment
python3 -m venv venv
source venv/bin/activate

# 2. Clone repository & install package
git clone https://github.com/daniel72584/grafeando.git
cd grafeando
pip install -e .

# 3. Configure MCP server for detected IDEs (or target specific platform: antigravity, cursor, claude, etc.)
grafeando install --project --platform auto
```

Targeting a specific platform:
```bash
grafeando install --project --platform antigravity
```
</details>

---

---

## 🌐 Interactive HTML Graph Explorer

You can generate a standalone, physics-based interactive graph visualization of your codebase that opens directly in your browser:

```bash
grafeando html
```

**Features:**
- 🎨 **Multi-Select Category Filters**: Toggle any combination of Controllers, Services, Schemas, Modules, Functions, and Components simultaneously.
- ⚡ **Configurable Node Limits**: Default 1,000 nodes with instant dropdown scaling (250, 500, 1k, 2.5k, 5k, Unlimited) prioritized by connection degree.
- 🔍 **Instant Search & Autocomplete**: Real-time camera zoom and neighbor highlighting for any function, class, or file.
- 💥 **Blast Radius Focus**: One-click to isolate and highlight multi-hop dependencies (1, 2, 3 hops) while hiding the rest of the codebase.
- 📊 **Node Inspector Drawer**: View file paths, line numbers, incoming callers, and outgoing dependencies with clickable navigation.


## 💬 How to use it

Just chat with your AI assistant normally! For example, ask:

- 💬 *"What files will break if I change the `user_id` column?"*
- 💬 *"Which React components use `<UserCard />`?"*
- 💬 *"Which SQL queries reference the `orders` table?"*

Your AI uses Grafeando automatically in the background to find the answer.

---

## 🛠️ Supported Languages & Technologies

- 🐍 **Python** (FastAPI, functions, models)
- 🟦 **TypeScript & JavaScript** (React, NestJS, TSX)
- 🐹 **Go** (Structs, methods)
- ☕ **Java** (Spring Boot, services)
- 🗄️ **SQL** (Tables, foreign keys, queries)
- 📝 **Docs & Data** (JSON, Markdown, CSV, PDF)

---

## 🤖 Prompt Guide for AI IDEs (Cursor, Claude, Gemini, Windsurf)

You can copy and paste these prompts directly into your AI Assistant chat:

### 1. 🚀 Master Setup Prompt (Run Once Per Repo)
> 💬 *"Set up Grafeando on this repository: run `grafeando install --project`, append the `## grafeando` rule to `AGENTS.md`, add `.grafeando_kuzu/` to `.gitignore`, and run `index_codebase('.')` to index the codebase."*

### 2. 🛡️ Safe Code Editing Prompt (Preventing Breakages)
> 💬 *"Before making any changes to `[Function/Class/File Name]`, check its blast radius using `get_blast_radius` to see all upstream callers and downstream dependencies. Ensure no breaking changes are introduced."*

### 3. 🗺️ Codebase Exploration Prompt
> 💬 *"Use Grafeando graph context to trace all files, services, and queries connected to `[Component/Service/Table Name]`."*

---

## 🔄 Automatic Git Auto-Indexing Hook

When you run `grafeando install --project`, Grafeando automatically installs a Git `post-commit` hook in `.git/hooks/post-commit`.

- **Automatic Updates**: Every time you or your AI assistant commit code, Grafeando re-indexes the AST graph in the background (~43 ms execution).
- **Zero API Cost**: Indexing uses local multi-language AST parsers with **0 LLM API calls and 0 token cost**.


<details>
<summary>⚙️ <b>Advanced Technical Details & Benchmarks (For Power Users)</b></summary>

- **Graph Engine**: In-memory Kùzu Graph Database + Multi-language AST parsers (`tree-sitter`, `sqlglot`, `pypdf`).
- **Performance**: Parses 2,300+ files in **43 ms** with **12–19 ms** graph query latency.
- **Token Reduction**: Returns ~100 tokens instead of sending 1.5 million tokens to LLM context windows.
- **Automated Tests**: Run `PYTHONPATH=. pytest tests`
</details>

---

## Possible Improvements:
- **Use a dedicated graph database (like Neo4j)**: With an external graph database service, searching, expanding, visualizing, and sharing across multiple repositories would be easier. But managing all that extra infrastructure for a single project is complete overkill.
- **Use embeddings**: Mixing vector embeddings with graph relationships would give a big advantage over purely static AST (Abstract Syntax Tree) parsing. However, it adds cost and complexity. It could be worth it if you have a single source of truth across many repositories, but not for a quick local setup.
- **Create specific parsers / rules**: Using LLMs to infer relationships—plus custom schemas and rules like YAML—would reduce hallucinations and give sharper context. The problem is the maintenance headache for every rule and stack. The tradeoff between being a simple generic tool for common repos versus a heavy customized solution for everything is something I don't want to take on right now.

## 📄 License

MIT License
