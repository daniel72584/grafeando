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
