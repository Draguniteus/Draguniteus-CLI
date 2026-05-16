# Draguniteus 🐉

**A dragon-themed autonomous CLI coding agent — forge software from intent.**

> *"With a breath of fire, I forge code from intent."*

<p align="center">
  <img src="https://img.shields.io/badge/version-0.1.0-gold?style=for-the-badge">
  <img src="https://img.shields.io/badge/python-3.12+-blue?style=for-the-badge">
  <img src="https://img.shields.io/badge/license-MIT-green?style=for-the-badge">
</p>

---

## What is Draguniteus?

Draguniteus is a fully autonomous CLI coding agent that understands your intent and executes complex multi-step engineering tasks in your terminal. It reads your codebase, writes and edits files, runs shell commands, manages git branches, spawns parallel sub-agents, and maintains project memory — all with dramatic dragon-themed flair.

It's built for developers who want an agent that:
- Works in a **real terminal** with **vim keybindings** and **mouse support**
- Can run **multiple specialized agents in parallel** and compare their results
- Plans large-scale **refactors** with rollback safety
- Learns your codebase's conventions and applies them consistently
- Connects to **MCP servers** for extensible tool integrations

---

## Features

### 🤖 Autonomous Agent Loop
Draguniteus runs a streaming tool-calling loop: it reads files, analyzes code, writes changes, runs tests, and iteratively refines until the task is complete. No single-shot prompts — it thinks, acts, observes, and adjusts.

### ⚡ Parallel Multi-Agent Orchestration
Run up to **8 concurrent sub-agents** in a live grid. Each agent gets its own worktree, streaming output, thinking display, and tool counter. Compare models head-to-head in **Arena Mode** when using different model tiers.

### 🖥️ Native Terminal UI
Fullscreen TUI with **Rich.Live** panels — flicker-free real-time updates per agent. **Vim keybindings** (`j/k/gg/G//n/N`) for navigation, **Shift+Tab** to cycle permission modes, **Ctrl+C** to interrupt all agents gracefully, Tab to cycle panel focus.

### 🧠 Project Memory
Drop a `DRAGUNITEUS.md` in any project root — it auto-loads your conventions, architecture decisions, and context on every session. Like a senior developer who read your docs before starting.

### 📋 Skills Framework
Markdown-based skills with YAML frontmatter. Describe any workflow (code review, commit strategy, refactoring pattern) as a skill and invoke it with `/skill <name>`. Built-in skills: feature-dev, frontend-design, mcp-integration, project-conventions, skill-development.

### 🛡️ Permission System
Never accidentally `rm -rf /`. Draguniteus ships with a rules engine that classifies operations as **ask/auto-approve/deny**. Dangerous commands get blocked, safe ones pass through, everything else prompts.

### 🔌 MCP Integration
Connect to any MCP server over stdio. Draguniteus auto-discovers tools, handles JSON-RPC handshakes, and routes MCP tool calls through the same streaming interface as native tools.

### 🗃️ Persistent Sessions
Every REPL session is saved as a JSONL transcript. Resume where you left off with `-c`. Sessions include token counts, cost tracking, and git branch state.

### 🔍 Code Intelligence
Semantic search across your codebase, symbol indexing, code explanation, and semantic graph for "find where this function is called" queries. Turns your editor into an intelligent codebase explorer.

### 🎯 Plugin System
Markdown-based plugins with PreToolUse/PostToolUse hooks. Write a `.md` file with YAML frontmatter — Draguniteus discovers it, registers its commands, and executes it as a system directive.

---

## Installation

```bash
git clone https://github.com/Draguniteus/Draguniteus-CLI.git
cd Draguniteus-CLI
pip install -e .

# Windows
python -m draguniteus --help
```

---

## First Launch

On first launch, enter your API key at the prompt. It's saved to `~/.draguniteus/settings.json`.

Or set it via environment variable:

```bash
export DRAGUNITEUS_API_KEY=your_key_here
python -m draguniteus
```

---

## Usage

### Interactive REPL
```bash
python -m draguniteus
❯ build a user auth system with JWT
```

### One-shot mode
```bash
python -m draguniteus -p "read pyproject.toml and explain the structure"
```

### Continue last session
```bash
python -m draguniteus -c
```

### Minimal theme (no ASCII art)
```bash
python -m draguniteus --minimal
```

### Piped input
```bash
cat error.log | python -m draguniteus "analyze this error"
```

---

## Slash Commands

| Command | Description |
|---------|-------------|
| `/help` | Show all commands |
| `/plan <task>` | Create and review a refactoring plan |
| `/effort [level]` | Set reasoning depth (low/medium/high/max) |
| `/compact` | Compress context window |
| `/memory` | Show/edit project memory |
| `/init` | Create DRAGUNITEUS.md in current project |
| `/agents` | List available sub-agents |
| `/orchestrate` | Run parallel multi-agent orchestration |
| `/new` | Start a new session |
| `/reset` | Clear session and start fresh |
| `/exit` | Exit |
| `/skills` | List all available skills |
| `/transcript` | Show session transcript summary |
| `/vim` | Toggle vim editing mode |
| `/doctor` | Run environment diagnostics |

---

## Multi-Agent Orchestration

```bash
/orchestrate "analyze codebase" \
  --agent explorer --task "explore project structure" \
  --agent security --task "find security issues" \
  --agent perf --task "find performance bottlenecks"
```

- **Arena Mode** activates automatically when ≥3 agents with different model tiers are used
- Arena shows a live comparison matrix: speed, quality score, tools used per agent
- **Ctrl+C** interrupts all agents. **Tab** cycles panel focus.

---

## Project Memory

Create a `DRAGUNITEUS.md` in any project:

```bash
python -m draguniteus
/init
```

Content example:
```markdown
# Project Conventions

## Stack
- Python 3.12, FastAPI, SQLite
- React 18 + Vite

## Architecture
- API routes in /src/api
- Business logic in /src/services
- No inline SQL — use the ORM

## Git Workflow
- branch per feature
- squash merge to main
- never force push
```

---

## Architecture

```
draguniteus/
├── src/draguniteus/
│   ├── cli.py              # REPL, slash commands, Typer app
│   ├── agent.py            # Streaming tool-calling loop
│   ├── client.py           # API client + retry logic
│   ├── config.py           # Layered config (env/file/CLI)
│   ├── orchestrator.py     # Multi-agent parallel executor
│   ├── session.py          # JSONL transcript + session store
│   ├── permissions.py      # Ask/Auto-approve/Deny rules engine
│   ├── rules.py            # Rule injection + injection sanitization
│   ├── hook_runner.py      # PreToolUse/PostToolUse plugin hooks
│   ├── tui/
│   │   ├── panels.py       # Rich.Grid multi-agent live panels
│   │   ├── arena.py        # Model comparison matrix (Arena Mode)
│   │   └── plan_viewer.py  # Collapsible refactor plan viewer
│   ├── tools/
│   │   ├── filesystem.py   # Read/Write/Edit/Glob/Grep
│   │   ├── shell.py        # Bash with 100KB output cap
│   │   ├── git.py          # Git operations
│   │   ├── mcp.py          # MCP client (stdio, 10MB line cap)
│   │   ├── mcp_tools.py    # MCP tool routing
│   │   ├── orchestrate.py  # Parallel agent orchestration tool
│   │   ├── review.py       # Multi-agent code review pipeline
│   │   ├── minimax.py      # Media generation (image/video/audio)
│   │   ├── code_intelligence.py  # Symbol index + semantic search
│   │   └── navigation.py   # Semantic code navigation
│   ├── memory/
│   │   ├── manager.py      # DRAGUNITEUS.md + daily notes
│   │   ├── pattern_library.py   # Learned tool sequence patterns
│   │   ├── conversation_archive.py  # Infinite context compression
│   │   └── semantic_graph.py  # Code relationship graph
│   ├── repl/
│   │   └── prompt_toolkit_input.py  # Vim keys + mouse support
│   ├── worktree/
│   │   └── manager.py      # Per-agent git worktree isolation
│   ├── plugins/
│   │   └── manager.py      # Plugin discovery + hook registration
│   ├── refactor/
│   │   └── autonomous.py    # Large-scale refactor planner + executor
│   ├── voice/
│   │   ├── input.py        # Voice listener
│   │   ├── output.py       # Voice speaker (TTS)
│   │   └── pair.py         # Pair programming mode
│   ├── skills/
│   │   └── eval.py         # Skill evaluation + benchmarking
│   ├── agents/
│   │   └── loader.py       # Agent discovery + loading
│   └── production/
│       └── monitor.py      # Health checks + webhook alerts
├── skills/                 # Markdown-based user skills
├── agents/                 # Custom sub-agent definitions
└── .draguniteus/           # Per-project config (auto-created)
```

---

## Configuration

Default config: `~/.draguniteus/settings.json`

```json
{
  "api_key": "your_key",
  "model": "MiniMax-M2.7",
  "base_url": "https://api.minimax.io/anthropic",
  "max_tokens": 8192,
  "temperature": 0.7,
  "permission_mode": "ask"
}
```

Override via CLI flags:
```bash
python -m draguniteus --model MiniMax-M2.7 --max-turns 20
```

---

## Environment Variables

| Variable | Description |
|----------|-------------|
| `DRAGUNITEUS_API_KEY` | Your API key |
| `DRAGUNITEUS_BASE_URL` | API base URL |
| `DRAGUNITEUS_MODEL` | Model name |
| `DRAGUNITEUS_MAX_TOKENS` | Max response tokens |
| `DRAGUNITEUS_CONFIG` | Path to config file |

---

## Output Size Guards

Draguniteus is hardened against runaway output:
- **Agent text**: 10 MB cap — truncates with `[...output truncated...]`
- **Tool results**: 500 KB cap per result
- **Bash output**: 100 KB cap (tail of output preserved)
- **MCP line reads**: 10 MB cap per line (prevents memory exhaustion)

---

## Keyboard Shortcuts (REPL Mode)

| Key | Action |
|-----|--------|
| `↑/↓` | History navigation |
| `Ctrl+R` | Reverse history search |
| `Tab` | Accept suggestion / cycle completions |
| `Shift+Tab` | Cycle permission mode (ask/acceptEdits/plan/auto) |
| `Ctrl+T` | Toggle task list |
| `Ctrl+O` | Show transcript viewer |
| `Ctrl+E` | Expand last tool results |
| `Ctrl+B` | Background current command |
| `Ctrl+C` | Interrupt all running agents |
| `! cmd` | Direct shell command |

---

## Memory & Context Management

- **Auto-archive**: After 40 conversation turns, Draguniteus compresses the oldest 20 turns via LLM summarization into a semantic archive. This keeps context fresh without losing history.
- **Cooldown**: Compression attempts are rate-limited to once per 30 seconds to prevent tight-looping.
- **Singleton patterns**: PatternLibrary and ConversationArchive are reused across turns — no per-turn disk reload.

---

🐉 **Breathing fire into code since 2026.**