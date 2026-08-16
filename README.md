# Grafeando 🕸️

> **A map of your codebase for your AI assistant.**

`grafeando` helps AI coding tools (like **Cursor**, **Claude**, **Windsurf**) understand how all your files and functions connect to each other.

---

## ❓ What problem does it solve?

When you ask an AI to edit your code:
- **Without Grafeando**: The AI guesses or reads random files, often breaking connected code without realizing it.
- **With Grafeando**: The AI sees a complete map of your project, knows **exactly what will break**, and edits code safely.

It also cuts AI token usage by **99.9%**, making AI responses **faster and much cheaper**.

---

## ⚡ Quickstart (2 Steps)

### 1. Install Grafeando
```bash
git clone https://github.com/daniel72584/grafeando.git
cd grafeando
pip install -e .
```

### 2. Connect to your AI tool
```bash
grafeando install
```
*(Automatically configures **Cursor, Claude Desktop, Gemini, Windsurf, Continue, and Codex**).*

---

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

## 📄 License

MIT License
