# Draguniteus 🐉

**A dragon-themed CLI coding agent powered by MiniMax**

> "With a breath of fire, I forge code from intent."

## What is Draguniteus?

Draguniteus is a CLI coding agent that replicates the full capabilities of Claude Code — but routes to **your MiniMax token plan** instead of Anthropic's API. It has all the tools, memory, and agentic behavior you need, wrapped in a fiery dragon theme.

## Features

- **Full tool suite**: Read, Write, Edit, Glob, Grep, Bash, GitStatus, GitDiff, GitCommit, GitPush, GitPRCreate
- **Streaming output**: Progressive markdown rendering in your terminal
- **Persistent sessions**: JSONL transcripts, continue where you left off with `-c`
- **Project memory**: DRAGUNITEUS.md (like CLAUDE.md) stores project conventions
- **Permission system**: Ask / Auto-approve / Deny rules for dangerous operations
- **Sub-agents**: Explore, Plan, Review, Debug built-in agents
- **Skills system**: Markdown-based extensible skills with YAML frontmatter
- **MCP support**: Connect to MCP servers for external tool integrations
- **Dragon theme**: Fiery ASCII art, red/gold/black colors, dramatic flair
- **Slash commands**: `/help`, `/plan`, `/effort`, `/compact`, `/memory`, `/init`, `/agents`

## Installation

```bash
cd draguniteus
pip install -e .
```

On Windows, use:
```bash
pip install -e .
python -m draguniteus --help
```

## First Launch

On first launch, Draguniteus will prompt for your MiniMax API key. It's saved to `~/.draguniteus/config.json`.

Set via environment variable:
```bash
export ANTHROPIC_API_KEY=sk-cp-2WQflDW-...
python -m draguniteus
```

## Usage

### Interactive REPL
```bash
python -m draguniteus
[D] your message here
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

## Slash Commands

| Command | Description |
|---------|-------------|
| `/help` | Show all commands |
| `/plan` | Enable planning mode |
| `/effort [level]` | Set reasoning depth |
| `/compact` | Compress context |
| `/memory` | Show DRAGUNITEUS.md |
| `/init` | Create DRAGUNITEUS.md |
| `/agents` | List sub-agents |
| `/new` | New session |
| `/exit` | Exit |

## Project Memory

Create a `DRAGUNITEUS.md` file in any project:
```bash
python -m draguniteus
/init
```

This file stores project conventions, architecture, and context — loaded automatically when you're in that directory.

## Permission System

Permissions are stored in `~/.draguniteus/permissions.json`. Default rules:
- Dangerous commands (rm -rf /, mkfs, etc.) → **deny**
- Safe commands (git, npm, pytest, ls, cat) → **auto_approve**
- Write/Edit → **ask**

## Architecture

```
draguniteus/
├── src/draguniteus/
│   ├── cli.py          # Typer REPL + commands
│   ├── agent.py        # Tool-calling agent loop
│   ├── client.py       # Anthropic SDK → MiniMax
│   ├── config.py       # Layered config
│   ├── theming.py      # Dragon ASCII + colors
│   ├── session.py      # JSONL transcript management
│   ├── permissions.py  # Ask/Auto-approve/Deny rules
│   ├── subagents.py    # Built-in + custom agents
│   ├── tools/
│   │   ├── filesystem.py  # Read/Write/Edit/Glob/Grep
│   │   ├── shell.py       # Bash execution
│   │   ├── git.py         # Git operations
│   │   ├── mcp.py         # MCP client
│   │   └── skills.py      # Skill loader
│   └── memory/
│       └── manager.py     # DRAGUNITEUS.md + daily notes
├── skills/              # User-extendable skills
├── agents/              # Custom agent definitions
└── .draguniteus/       # Per-project (auto-created)
```

## API Configuration

By default, Draguniteus routes to MiniMax's Anthropic-compatible endpoint:
- **Base URL**: `https://api.minimax.io/anthropic`
- **Default model**: `MiniMax-M2.7`
- **API key**: Set via `ANTHROPIC_API_KEY` env var or config file

Override via CLI:
```bash
python -m draguniteus --api-key sk-xxx --model MiniMax-M2.7
```

Or in `~/.draguniteus/config.json`:
```json
{
  "api_key": "sk-cp-...",
  "model": "MiniMax-M2.7",
  "base_url": "https://api.minimax.io/anthropic"
}
```

---

🐉 *Breathing fire into code since 2026.*