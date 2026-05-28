# DRAGUNITEUS.md — Project Memory

## What is Draguniteus?

Draguniteus is a dragon-themed autonomous CLI coding agent powered by MiniMax's M2.7 model. It provides an interactive REPL for coding, debugging, and building software projects with multi-agent orchestration, persistent memory, and advanced tool execution.

---

## Quick Start

```bash
# Install
pip install -e .

# Start REPL
draguniteus

# One-shot mode
draguniteus main "create a FastAPI server with JWT auth"
```

---

## Slash Commands

| Command | Description |
|---------|-------------|
| `/think` | Force deep reasoning mode for the next turn |
| `/fast` | Force direct answer mode (skip thinking) for the next turn |
| `/effort [low\|medium\|high\|xhigh\|max\|auto]` | Set effort level. `auto` uses thinking router to pick high (analyze/debug/plan) or medium (create/write/fix) |
| `/workflow [status\|plan\|exec\|verify\|iterate]` | View or control the agentic workflow phase |
| `/preview [stop]` | Start/stop the live HTML preview server (port 7420) |
| `/checkpoint [list\|load\|delete]` | Manage session checkpoints for crash recovery |
| `/tools [stats\|list]` | View tool usage statistics and registered custom tools |
| `/critique` | Run self-improvement critique on the last task |
| `/memory [search <query>]` | Search ChromaDB vector memory for past decisions |
| `/git [status\|commit\|push\|auto\|log]` | Git commands and auto-commit |
| `/arena <task> [model1] [model2]` | Head-to-head model comparison |

---

## Architecture

### Core Components

- **Agent** (`agent.py`): Main agent loop — `stream_one_turn()` for REPL, `run_one_turn()` for one-shot. Handles message building, thinking router, developer role, tool execution, self-correction.
- **StreamingDisplay** (`streaming_display.py`): Rich TUI with animated thinking indicators, tool progress bars, phase badges.
- **HookRunner** (`hook_runner.py`): Executes plugin hooks for PreToolUse, PostToolUse, Stop, SessionStart/End, UserPromptSubmit, PreCompact, Notification.
- **Config** (`config.py`): Settings for model, effort, thinking router, checkpoint intervals, nested tool depth.

### Memory Layers

1. **Short-term** (`session`): Current REPL messages, accumulated in `messages` list
2. **Medium-term** (`daily`): `memory/YYYY-MM-DD.md` — today's notes, written by `/critique` and automatically
3. **Long-term** (`project`): `DRAGUNITEUS.md` in project root — architecture decisions, patterns, constraints
4. **Vector** (ChromaDB): Semantic search index at `.draguniteus/chroma_db/<project-hash>/` — code decisions, conversation summaries, patterns. Queried via `MemoryManager.load_for_agent(query)` when system prompt is built.

### Tool System

Tools are defined in `tools/`:
- **NestedToolExecutor** — executes tool call graphs with 5-level depth, exponential backoff retry (transient: timeout, connection refused, rate limit, 503/502/429; permanent: not found, invalid, permission denied, 400/401/403/404)
- **ToolReflection** — tracks per-tool stats (call count, success rate, latency, failure reasons) in `~/.draguniteus/tool_stats.json`
- **Dynamic Tools** (`dynamic.py`) — user-defined tools persisted to `~/.draguniteus/custom_tools/<name>.json`

### Thinking Router

Hybrid routing in `thinking_router.py`:
- **Reasoning tasks** (thinking=ON): analyze, debug, plan, explain why, investigate, assess, design, evaluate, review, understand, diagnose
- **Direct tasks** (thinking=OFF): write, create, add, fix, format, list, show, get, fetch, run, build, make, delete, remove
- **Token budget**: if context >60% full, skip thinking overhead
- **Tool complexity**: if >3 tools available, enable thinking
- Override via `/think` and `/fast` slash commands

### Self-Correction

`self_correction.py` — Write→Verify→Fix loop:
1. After Write/Edit tools, `SelfCorrectionEngine.record_write()` queues the file
2. After tool execution, `check_and_fix()` runs verification (PythonSyntaxCheck via py_compile, ESLintCheck, ShellcheckCheck)
3. On failure, injects error context into messages for a fix attempt
4. Max 3 iterations before surfacing to user
5. On success, learns tool sequence in PatternLibrary

### Agentic Workflow

`workflows/agentic_workflow.py` — state machine:
```
PLANNING → EXECUTING → VERIFYING → ITERATING → DONE
```
- Phase badges shown in streaming display: `[PLAN]`, `[EXEC]`, `[VERIFY]`, `[ITERATE]`, `[DONE]`
- Serializable `WorkflowState` with plan steps, completed steps, verification results
- Checkpoint integration for crash recovery

---

## Configuration (`.draguniteus/settings.json`)

```json
{
  "model": "MiniMax-M2.7",
  "effort": "medium",
  "checkpoint_every": 5,
  "nested_tool_max_depth": 5,
  "thinking_router_enabled": true,
  "developer_role_enabled": true,
  "self_improvement_enabled": true,
  "chromadb_enabled": true,
  "preview_server_enabled": false
}
```

---

## Checkpoint System

Checkpoints save agent state to `.draguniteus/checkpoints/<session_id>/step_<N>.json`:
- `session_id`, `step_count`, `phase`, `messages` (truncated to last 50 turns), `workflow_state`, `tracked_files`, `effort`, `model`
- Atomic writes (temp file + rename) — safe on Windows
- Auto-saves every N turns (configurable `checkpoint_every`)
- Resume with `/checkpoint load <session_id>`

---

## MiniMax Models Available

| Model | Context | Best For |
|-------|---------|----------|
| `MiniMax-M2.7` | 200k | Complex reasoning, recursive self-improvement |
| `MiniMax-M2.5` | — | Code generation and refactoring |
| `MiniMax-M2.1` | — | Code generation/refactoring, enhanced reasoning |
| `MiniMax-M2` | 200k | Agentic capabilities, function calling |

---

## Project Structure

```
src/draguniteus/
├── agent.py              # Main agent loop
├── cli.py                # REPL entry point, slash commands
├── client.py             # MiniMax API client wrapper
├── config.py             # Settings management
├── streaming_display.py  # Rich TUI panels
├── hook_runner.py        # Plugin hook system
├── thinking_router.py    # Hybrid thinking/direct routing
├── role_adapter.py      # Developer role message injection
├── checkpoint.py         # Crash recovery checkpoints
├── self_correction.py    # Write→Verify→Fix loop
├── self_improvement.py   # Post-task critique
├── orchestrator.py       # Multi-agent orchestration
├── memory/
│   ├── manager.py       # All memory layers
│   ├── vector_store.py   # ChromaDB integration
│   ├── semantic_graph.py
│   └── pattern_library.py
├── workflows/
│   └── agentic_workflow.py  # PLANNING→EXEC→VERIFY→ITERATE→DONE
├── tools/
│   ├── nested_tool_executor.py
│   ├── dynamic.py        # Custom tool builder
│   └── reflection.py     # Per-tool stats tracking
└── preview/
    └── server.py        # Live HTML preview on port 7420
```

---

## Key Behaviors

- **Thinking mode**: Models generate `<think>` blocks when routing decides thinking=ON. Streaming display shows animated thinking indicators.
- **Developer role**: Structured context injected into system prompt (active files, tools, project constraints, current mode)
- **Tool reflection**: Every tool call is tracked — call count, success/failure, latency. View with `/tools stats`.
- **Notifications**: After long operations, `send_notification()` fires Notification hooks so plugins can alert the user.
- **Context compaction**: When messages approach context limit, `PreCompact` hook fires and messages are summarized.

---

## Arena Mode (Head-to-Head Agent Comparison)

`/arena [task] [model1] [model2]`

Runs multiple agents simultaneously on the same task and compares:
- **Correctness**: Does the code run? Tests pass?
- **Style**: Readability, structure, best practices
- **Speed**: Time to first tool call, total duration
- **Token efficiency**: Tokens used vs. output quality

Models compete in rounds. Winner advances. Final bracket shows champion.
Uses 4 MiniMax models by default: M2.7, M2.5, M2.1, M2.

---

## Git Commands

`/git [status|commit <msg>|push|auto|log|branch|stash]`

| Command | Description |
|---------|-------------|
| `/git status` | Show working tree status |
| `/git commit <msg>` | Commit with a message |
| `/git push` | Push to remote |
| `/git auto` | Auto-commit all staged changes (auto-generates message) |
| `/git log` | Show recent commits |
| `/git branch` | List branches |
| `/git stash` | Stash current changes |

**GitAutoCommit tool**: Also available as a tool for automatic commits after Write/Edit operations.

---

## Tips

- Use `/effort auto` and let the thinking router decide — it classifies tasks automatically
- After writing code, Draguniteus auto-verifies Python syntax via py_compile
- ChromaDB vector memory accumulates project-specific patterns — the more you work in a project, the smarter the retrieval
- `/critique` after complex tasks updates daily memory and PatternLibrary
- Checkpoints auto-save every 5 turns — if Draguniteus crashes, resume with `/checkpoint load`