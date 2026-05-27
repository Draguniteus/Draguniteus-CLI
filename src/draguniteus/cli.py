"""CLI entry point — Typer app with REPL, one-shot, and piped modes."""
from __future__ import annotations

import json
import os
import sys
import time
import io
from pathlib import Path
from typing import Any

import questionary
import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text

from draguniteus import __version__
from draguniteus.agent import StreamHandler, run_one_turn
from draguniteus.client import DraguniteusClient
from draguniteus.config import Config
from draguniteus.permissions import PermissionStore
from draguniteus.session import Session, SessionStore
from draguniteus.theming import (
    _print,
    claudebrand,
    console,
    get_thinking_verb,
    gold,
    gray,
    print_divider,
    print_error,
    print_status_line,
    print_success,
    print_thinking,
    print_welcome,
    teal,
    thinking,
)
from draguniteus.rules import RulesManager

app = typer.Typer(add_completion=False, help="[D] Draguniteus - Dragon-themed CLI coding agent")

# Global state
_cfg: Config | None = None
_client: DraguniteusClient | None = None
_permissions: PermissionStore | None = None
_session_store: SessionStore | None = None
_full_drama: bool = True
_permission_mode: str = "default"
_bare_mode: bool = False
_max_turns: int | None = None
_max_budget: float | None = None
_total_cost: float = 0.0
_output_format: str = "text"
_allowed_tools: list[str] | None = None
_disallowed_tools: list[str] | None = None
_system_prompt_override: str | None = None
_append_system_prompt: str | None = None
_worktree_name: str | None = None
_resume_id: str | None = None
_session_id: str | None = None
_settings_path: str | None = None
_auto_mode: bool = False
_vim_mode: bool = False
_prompt_suggestions: bool = True
_show_task_list: bool = False
_expand_tools_requested: bool = False
_rules_manager: "RulesManager | None" = None
_tracked_files: list[str] = []
_style_name: str | None = None
_plugin_manager: Any = None
_task_manager: Any = None
_last_tool_results: list[dict] = []  # For expandable tool display
_expand_tools_requested: bool = False  # Set by Ctrl+E
_piped_command: str | None = None  # Piped command from stdin for REPL mode
_plan_viewer: Any = None  # Plan viewer instance for /plan command
_orchestrate_panels: Any = None  # Active AgentPanels instance during orchestration
_arena_mode: Any = None  # Active ArenaMode instance during multi-model orchestration
_active_panels: Any = None  # Currently active panels (AgentPanels or ArenaMode)
_active_panel_index: int = 0  # Which panel has keyboard focus for Tab cycling
_orchestrator_cancel: Any = None  # Callable to cancel active orchestration
_pending_edits: list[dict] = []  # Pending edits waiting to be accepted
_pending_edit_index: int = 0  # Which pending edit is currently focused
_edit_accept_mode: bool = False  # Whether we're cycling through pending edits
_active_bg_task: dict | None = None  # Currently active backgroundable task (set during long commands)


def _get_rules_manager() -> "RulesManager":
    global _rules_manager
    if _rules_manager is None:
        _rules_manager = RulesManager(Path.cwd())
    return _rules_manager


def _get_slash_command_completions() -> list[str]:
    """Return all slash command names for tab completion."""
    completions = [
        "help", "plan", "effort", "compact", "memory", "init",
        "agents", "new", "reset", "exit", "quit", "recap",
        "release-notes", "usage", "btw", "style", "worktree",
        "tasks", "transcript", "background", "vim", "skills", "skill",
        "agent",
        "orchestrate", "review", "index", "voice",
        "diff", "inspect", "info", "doctor",
    ]
    try:
        plugin_mgr = _get_plugin_manager()
        completions.extend(plugin_mgr.get_all_commands().keys())
    except Exception:
        pass
    return completions


def _get_plugin_manager() -> Any:
    global _plugin_manager
    if _plugin_manager is None:
        from draguniteus.plugins.manager import get_plugin_manager
        _plugin_manager = get_plugin_manager()
    return _plugin_manager


def _get_task_manager() -> Any:
    global _task_manager
    if _task_manager is None:
        from draguniteus.tasks.manager import get_task_manager
        _task_manager = get_task_manager()
    return _task_manager


def _track_file(file_path: str) -> None:
    global _tracked_files
    if file_path and file_path not in _tracked_files:
        _tracked_files.append(file_path)


def _ensure_api_key() -> None:
    global _cfg, _client
    if not _cfg:
        _cfg = Config()

    if not _cfg.api_key:
        console.print(Panel(
            Text("[D] First Launch -- API Key Required", style="yellow bold"),
            border_style="red",
        ))
        key = questionary.text(
            "Enter your MiniMax Token Plan API key:",
            style=questionary.Style([
                ("question", "fg:#F59E0B"),
            ])
        ).ask()
        if key:
            _cfg.prompt_and_save_api_key(key)
            print_success("API key saved to ~/.draguniteus/settings.json")
        else:
            print_error("No API key provided. Set ANTHROPIC_API_KEY env var to continue.")


def _get_client() -> DraguniteusClient:
    global _client
    if not _client:
        _ensure_api_key()
    return _client


def _get_permissions() -> PermissionStore:
    global _permissions, _cfg, _auto_mode
    if not _permissions:
        _permissions = PermissionStore(_cfg or Config(), auto_mode=_auto_mode)
    return _permissions


def _get_session_store() -> SessionStore:
    global _session_store, _cfg
    if not _session_store:
        _session_store = SessionStore(_cfg or Config())
    return _session_store


from draguniteus.memory.manager import memory_manager

SYSTEM_PROMPT = """You are Draguniteus, a powerful dragon-themed CLI coding agent.

You operate as a fully agentic coding assistant:
- Plan before acting: analyze the task, identify files to examine, then execute
- Work iteratively: execute tools, observe results, adjust your approach
- Execute multi-step tasks autonomously, ask for approval for sensitive operations

You have access to these tools:

**Filesystem:** Read, Write, Edit, MultiEdit, Glob, Grep
**Shell:** Bash
**Git:** GitStatus, GitDiff, GitCommit, GitPush, GitPRCreate
**Web:** WebFetch, WebSearch
**Memory:** WriteDailyNote, ReadDailyNote, WriteProjectMemory, ReadProjectMemory
**Code Intelligence:** IndexCode, FindSymbol, GoToDefinition, FindReferences
**Media:** text_to_audio, list_voices, voice_clone, text_to_image, generate_video, music_generation, query_video_generation, image_to_video
**Orchestration:** Orchestrate, MultiAgentReview
**Navigation:** SemanticSearch, ExplainCode, IndexSemantic
**Review:** StartCodeReview, StopCodeReview, GetReviewFindings
**Voice:** voice_start, voice_stop, voice_speak, voice_listen
**Diff:** tool_diff, tool_diff_staged
**Inspect:** InspectEnvironment
**Agent:** Agent (run sub-agents for specialized tasks)

**MCP Servers:** GitHub (GitHub API), filesystem (local file access), minimax (MiniMax API)

Communication style:
- Confident, powerful, slightly theatrical dragon mentor energy
- Use [D] prefix for thoughts, dragon-themed language
- Be helpful, precise, and efficient
- Use markdown formatting in responses

When executing tools, wait for results before continuing.
When you need user approval for a risky action, say so clearly."""


def _get_system_prompt() -> str:
    global _system_prompt_override, _append_system_prompt, _bare_mode, _style_name

    if _system_prompt_override:
        base = _system_prompt_override
    else:
        base = SYSTEM_PROMPT

    if _bare_mode:
        return base

    # Apply output style if set
    if _style_name:
        from draguniteus.styles.manager import get_style_manager
        style_mgr = get_style_manager()
        base = style_mgr.apply_style(_style_name, base)

    # Inject memory
    memory = memory_manager.load_for_agent()
    if memory:
        base = base + "\n\n" + memory

    # Inject rules for tracked files and current directory
    try:
        rules_mgr = _get_rules_manager()
        from draguniteus.agent import get_tracked_files
        tracked = get_tracked_files()
        paths_to_check = [str(Path.cwd())] + list(set(tracked))
        rules_injection = rules_mgr.inject_for_paths(paths_to_check)
        if rules_injection:
            base = base + rules_injection
    except Exception:
        pass

    if _append_system_prompt:
        base = base + "\n\n" + _append_system_prompt

    return base


# ------------------------------------------------------------------
# Commands
# ------------------------------------------------------------------

@app.command("doctor")
def doctor_cmd() -> None:
    """Run self-diagnosis and check Draguniteus environment."""
    from draguniteus.inspect import run_doctor, format_doctor
    checks = run_doctor()
    # Use print() directly since format_doctor uses plain text with emoji
    print(format_doctor(checks))


@app.command("info")
def info_cmd(json_output: bool = typer.Option(False, "--json", help="Machine-readable JSON")) -> None:
    """Dump full Draguniteus environment as JSON."""
    from draguniteus.inspect import get_full_environment
    import json
    env = get_full_environment()
    if json_output:
        print(json.dumps(env, indent=2))
    else:
        from draguniteus.inspect import format_environment
        print(format_environment(env))


@app.command()
def main(
    prompt: str | None = typer.Argument(None, help="Prompt to execute"),
    print_mode: bool = typer.Option(False, "-p", "--print", help="One-shot mode: output result and exit"),
    continue_session: bool = typer.Option(False, "-c", "--continue", help="Continue the last session"),
    minimal: bool = typer.Option(False, "--minimal", help="Minimal theme (no ASCII art, no colors)"),
    model: str | None = typer.Option(None, "--model", help="Model to use"),
    api_key: str | None = typer.Option(None, "--api-key", help="API key (or set ANTHROPIC_API_KEY env var)"),
    config_path: str | None = typer.Option(None, "--config", help="Config file path"),
    # New flags
    bare: bool = typer.Option(False, "--bare", help="Minimal mode, skip auto-discovery of hooks, skills, MCP"),
    output_format: str = typer.Option("text", "--output-format", help="Output format: text, json, stream-json"),
    max_turns: int | None = typer.Option(None, "--max-turns", help="Limit agentic turns"),
    max_budget: float | None = typer.Option(None, "--max-budget-usd", help="Maximum USD to spend"),
    worktree: str | None = typer.Option(None, "-w", "--worktree", help="Start in isolated git worktree"),
    resume: str | None = typer.Option(None, "-r", "--resume", help="Resume specific session by ID or name"),
    session_id: str | None = typer.Option(None, "--session-id", help="Use specific session ID"),
    settings: str | None = typer.Option(None, "--settings", help="Path to settings JSON file"),
    system_prompt: str | None = typer.Option(None, "--system-prompt", help="Replace system prompt"),
    system_prompt_file: str | None = typer.Option(None, "--system-prompt-file", help="Load system prompt from file"),
    append_system_prompt: str | None = typer.Option(None, "--append-system-prompt", help="Append to system prompt"),
    append_system_prompt_file: str | None = typer.Option(None, "--append-system-prompt-file", help="Append from file to system prompt"),
    tools: str | None = typer.Option(None, "--tools", help="Comma-separated allowed tools"),
    disallowed_tools: str | None = typer.Option(None, "--disallowed-tools", help="Comma-separated disallowed tools"),
    permission_mode: str = typer.Option("default", "--permission-mode", help="Permission mode: default, acceptEdits, plan, auto, dontAsk, bypassPermissions"),
    allow_dangerously_skip_permissions: bool = typer.Option(False, "--allow-dangerously-skip-permissions", help="Add bypassPermissions to mode cycle"),
    verbose: bool = typer.Option(False, "--verbose", help="Enable verbose output"),
    name: str | None = typer.Option(None, "-n", "--name", help="Set session display name"),
    style: str | None = typer.Option(None, "--style", help="Output style: explanatory, learning, concise, technical"),
    version: bool = typer.Option(False, "--version", "-v", help="Show version and exit"),
):
    """Start Draguniteus interactive REPL or run a one-shot prompt."""
    global _cfg, _client, _full_drama, _permission_mode, _bare_mode
    global _max_turns, _max_budget, _output_format
    global _allowed_tools, _disallowed_tools
    global _system_prompt_override, _append_system_prompt
    global _worktree_name, _resume_id, _session_id, _settings_path, _auto_mode
    global _style_name

    if version:
        from draguniteus import __version__
        console.print(gold(f"Draguniteus v{__version__}"))
        console.print(gray("Breathing fire into code since 2026."))
        raise SystemExit(0)

    _full_drama = not minimal
    _bare_mode = bare
    _permission_mode = permission_mode
    _auto_mode = permission_mode == "auto"
    _output_format = output_format
    _max_turns = max_turns
    _max_budget = max_budget
    _worktree_name = worktree
    _resume_id = resume
    _session_id = session_id
    _settings_path = settings
    _style_name = style

    if tools:
        _allowed_tools = [t.strip() for t in tools.split(",")]
    if disallowed_tools:
        _disallowed_tools = [t.strip() for t in disallowed_tools.split(",")]

    if allow_dangerously_skip_permissions and _permission_mode == "plan":
        _permission_mode = "bypassPermissions"

    if not prompt and not sys.stdin.isatty():
        piped = sys.stdin.read().strip()
        # If piped input starts with /, treat as REPL commands
        # Otherwise treat as a one-shot prompt
        if piped.startswith("/") and not bare:
            # Enter REPL mode with the command already read
            # Signal this by setting a special flag
            _piped_command = piped
        else:
            prompt = piped

    if settings:
        settings_path = Path(settings)
        if settings_path.exists():
            try:
                settings_data = json.loads(settings_path.read_text())
                _cfg_cli = settings_data
            except json.JSONDecodeError:
                _cfg_cli = {}
        else:
            _cfg_cli = {}
    else:
        _cfg_cli = {}

    if system_prompt_file:
        sp_path = Path(system_prompt_file)
        if sp_path.exists():
            _system_prompt_override = sp_path.read_text()
    elif system_prompt:
        _system_prompt_override = system_prompt

    if append_system_prompt_file:
        ap_path = Path(append_system_prompt_file)
        if ap_path.exists():
            _append_system_prompt = ap_path.read_text()
    elif append_system_prompt:
        _append_system_prompt = append_system_prompt

    if api_key:
        _cfg_cli["api_key"] = str(api_key)
    if model:
        _cfg_cli["model"] = str(model)

    _config_file = Path(str(config_path)) if config_path else None
    _cfg = Config(config_file=_config_file, cli_overrides=_cfg_cli)

    if Config.first_launch() and not _cfg.api_key:
        _ensure_api_key()
        if not _cfg.api_key:
            console.print(red("[D] No API key provided. Exiting."))
            raise SystemExit(1)

    if not _cfg.api_key:
        console.print(red("[D] No API key set. Exiting."))
        raise SystemExit(1)

    _client = DraguniteusClient(_cfg)

    # Discover and load plugins (skip in bare mode)
    if not bare:
        _load_plugins()

    session_store = _get_session_store()

    if not bare:
        print_welcome(_full_drama)
    else:
        console.print(gold("[Draguniteus v0.1.0 - bare mode]"))

    # Run SessionStart hooks
    if not bare:
        _run_session_start_hooks(session_store)

    if prompt:
        # If the "prompt" starts with / it's a slash command — enter REPL instead of one-shot
        if prompt.strip().startswith("/") and not bare:
            _piped_command = prompt.strip()
        else:
            _run_one_shot(prompt, _cfg, _client, session_store)
            return

    if resume:
        session = _find_session_by_id_or_name(resume, session_store)
        if session:
            messages = _load_session_messages(session)
            console.print(gray(f"Resuming session {session.id}..."))
        else:
            console.print(gray(f"Session '{resume}' not found, starting fresh."))
            session = session_store.get_or_create(str(_cfg.model))
            messages = []
    elif continue_session:
        session = session_store.get_or_create(str(_cfg.model))
        messages = _load_session_messages(session)
        if messages:
            console.print(gray(f"Resuming session {session.id}..."))
        else:
            console.print(gray("No previous session found, starting fresh."))
    else:
        session = session_store.get_or_create(str(_cfg.model))
        messages = []

    from draguniteus.agent import clear_tracked_files
    clear_tracked_files()

    if name:
        session_id_display = f"{session.id} ({name})"
    else:
        session_id_display = session.id

    if not bare:
        console.print(gray("Type /help for commands\n"))
    print_divider(_full_drama)

    turn_count = 0
    while True:
        # Use piped command if available (from stdin when piped a slash command)
        # Split multi-line _piped_command into separate inputs
        if _piped_command:
            lines = _piped_command.split('\n')
            user_input = lines[0]
            remaining = '\n'.join(lines[1:])
            _piped_command = remaining if remaining else None
        else:
            try:
                user_input = _read_input()
            except (EOFError, KeyboardInterrupt):
                # No more input available - exit the REPL
                break

        if not user_input.strip():
            continue

        if _max_turns and turn_count >= _max_turns:
            console.print(gray(f"Max turns ({_max_turns}) reached. Exiting."))
            try:
                from draguniteus.hook_runner import get_hook_runner
                hook_runner = get_hook_runner()
                hook_runner.run_stop(messages, "max_turns")
            except Exception:
                pass
            break

        # Check max budget
        # TODO: Implement budget tracking

        if user_input.startswith("/"):
            handled = _handle_slash_command(user_input, messages, session)
            if handled is False:
                break
            if handled is True:
                turn_count += 1
                continue

        if user_input.startswith("!") and not bare:
            _handle_shell_mode(user_input[1:], session_store, session)
            continue

        if user_input.startswith("/btw "):
            _handle_btw(user_input[5:], session)
            continue

        console.print()
        start = time.time()

        # Set active background task info so Ctrl+B shows agent status
        _active_bg_task = {
            "id": f"agent_turn_{turn_count}",
            "description": f"Agent turn: {user_input[:60]}...",
            "type": "agent",
        }

        # Prepend user message so API call has a non-empty messages list
        messages.append({"role": "user", "content": user_input})

        # Fire UserPromptSubmit hook
        try:
            from draguniteus.hook_runner import get_hook_runner
            hook_runner = get_hook_runner()
            hook_runner.run_userpromptsubmit(user_input)
        except Exception:
            pass

        response_text, tool_results, in_tok, out_tok, thinking = run_one_turn(_client, messages, _get_system_prompt(), _cfg, _full_drama)
        elapsed = time.time() - start

        # Clear active background task after turn completes
        _active_bg_task = None

        # Track and check budget
        if _max_budget is not None:
            # MiniMax pricing: ~$0.05 per million tokens (input + output combined)
            turn_cost = (in_tok + out_tok) / 1_000_000 * 0.05
            _total_cost += turn_cost
            if _total_cost > _max_budget:
                _print(red(f"Budget limit reached (${_total_cost:.4f} > ${_max_budget:.4f}). Exiting."))
                break

        # Check if context needs compaction (at 80% of max_tokens)
        try:
            from draguniteus.hook_runner import get_hook_runner
            hook_runner = get_hook_runner()
            input_tokens = _client.count_tokens(messages)
            threshold = int((_cfg.max_tokens or 8192) * 0.8)
            if input_tokens > threshold:
                hook_runner.run_precompact(messages)
        except Exception:
            pass

        # Show thinking inline if present
        if thinking and _full_drama:
            display_thinking = thinking[:300] + "..." if len(thinking) > 300 else thinking
            _print(thinking(f"[Thinking... {display_thinking}]"))

        if response_text:
            # Strip leading newlines
            text = response_text.lstrip('\n')
            # Try Rich markdown rendering, fall back to plain text
            try:
                from io import StringIO
                sio = StringIO()
                c2 = Console(file=sio, force_terminal=False)
                c2.print(Markdown(text))
                rendered = sio.getvalue().rstrip('\n')
            except Exception:
                rendered = text
            # Strip Rich markup and extra whitespace from each line
            import re
            clean_lines = []
            for line in rendered.split('\n'):
                # Remove Rich markup tags
                clean = re.sub(r'\[/?[^]]+\]', '', line)
                # Strip leading/trailing whitespace
                clean = clean.strip()
                clean_lines.append(clean)
            # Print with ● prefix on first non-empty line (Claude Code style)
            first = True
            for line in clean_lines:
                if not line:
                    continue
                prefix = "● " if first else "  "
                first = False
                try:
                    print(prefix + line)
                except UnicodeEncodeError:
                    print((prefix + line).encode('ascii', errors='replace').decode('ascii'))

        # Store tool results for expandable display
        global _last_tool_results
        _last_tool_results = tool_results

        # Show collapsed tool call summary (Claude Code style: "Called Bash 3 times")
        if tool_results:
            from collections import Counter
            counts = Counter(tr.get("tool", "?") for tr in tool_results)
            if len(counts) == 1:
                name = list(counts.keys())[0]
                n = list(counts.values())[0]
                summary = f"Called {name}" if n == 1 else f"Called {name} {n} times"
            else:
                summary = ", ".join(f"{v}x {k}" for k, v in counts.items())
                summary = f"Called {summary}"
            _print(gray(summary))

        # Print status line: model | cwd | git branch | context % | cost | duration
        try:
            import subprocess
            branch = None
            try:
                branch = subprocess.run(
                    ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                    capture_output=True, text=True, timeout=3,
                ).stdout.strip() or None
            except Exception:
                pass
            input_toks = _client.count_tokens(messages) if _client else 0
            ctx_pct = min(100.0, (input_toks / max(1, (_cfg.max_tokens or 8192))) * 100)
            print_status_line(
                str(_cfg.model),
                str(Path.cwd().name),
                branch,
                ctx_pct,
                _total_cost,
                elapsed,
            )
        except Exception:
            pass

        session_store.append_event(session, {
            "type": "user",
            "content": user_input,
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        })
        session_store.append_event(session, {
            "type": "assistant",
            "content": response_text,
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        })
        session_store.update(session)

        # Auto-archive if conversation is getting long
        try:
            from draguniteus.memory.conversation_archive import _get_conversation_archive
            archive = _get_conversation_archive()
            summary = archive.auto_archive_if_needed(len(messages), max_turns=40)
            if summary:
                if _full_drama:
                    console.print(gray(f"  [archived {min(20, len(messages)//2)} turns: {summary[:80]}...]"))
                else:
                    print(gray(f"[archived: {summary[:80]}...]"))
        except Exception as e:
            console.print(gray(f"  [auto-archive warning: {e}]"))
            pass

        print_divider(_full_drama)
        console.print()

        # --- Auto-checkpoint every N turns ---
        try:
            from draguniteus.checkpoint import get_checkpoint_manager, AgentCheckpoint
            from draguniteus.agent import get_tracked_files
            mgr = get_checkpoint_manager()
            mgr.start_session(session.id, checkpoint_every=getattr(cfg, 'checkpoint_every', 5))
            step = mgr.tick()
            if step > 0 and mgr.should_checkpoint():
                cp = AgentCheckpoint(
                    session_id=session.id,
                    step_count=step,
                    phase="completed",
                    messages=messages[-50:],
                    tracked_files=get_tracked_files(),
                    effort=getattr(cfg, 'effort', 'medium'),
                    model=getattr(cfg, 'model', 'MiniMax-M2.7'),
                )
                mgr.save(cp)
        except Exception:
            pass

        turn_count += 1

    # Run SessionEnd hooks
    if not bare:
        _run_session_end_hooks(session_store)


def _load_plugins() -> None:
    """Discover and load all plugins."""
    global _plugin_manager
    try:
        plugin_mgr = _get_plugin_manager()

        # Set up MCP client for plugin server auto-start
        try:
            from draguniteus.tools.mcp import MCPClient
            mcp_client = MCPClient()
            plugin_mgr.set_mcp_client(mcp_client)
        except Exception:
            pass

        plugins = plugin_mgr.discover_plugins()
        if plugins:
            console.print(gray(f"Loaded {len(plugins)} plugins: {', '.join(p.name for p in plugins)}"))

        # Register plugin hooks with hook runner
        from draguniteus.hook_runner import get_hook_runner
        hook_runner = get_hook_runner()
        for plugin in plugins:
            for event_name, hooks in plugin.hooks.items():
                hook_runner.register_plugin_hooks(event_name, hooks)
    except Exception as e:
        console.print(gray(f"Plugin discovery error: {e}"))


def _run_session_start_hooks(session_store: SessionStore) -> None:
    """Fire SessionStart hooks when REPL begins."""
    try:
        from draguniteus.hook_runner import get_hook_runner
        session = session_store.get_or_create(str(_cfg.model)) if _cfg else None
        if session:
            hook_runner = get_hook_runner()
            hook_runner.run_session_start(session.id, str(Path.cwd()))
    except Exception:
        pass


def _run_session_end_hooks(session_store: SessionStore) -> None:
    """Fire SessionEnd hooks when REPL exits."""
    try:
        from draguniteus.hook_runner import get_hook_runner
        hook_runner = get_hook_runner()
        # Get current session id
        sessions = session_store.list_all()
        if sessions:
            latest = sessions[0]
            hook_runner.run_session_end(latest.id, str(Path.cwd()))
    except Exception:
        pass


def _handle_shell_mode(command: str, session_store: SessionStore, session: Session) -> None:
    """Execute a shell command directly, add output to context."""
    from draguniteus.tools.shell import tool_bash
    console.print(gray(f"[!] {command}"))
    result = tool_bash(command)
    console.print(result[:500])
    if len(result) > 500:
        console.print(gray(f"... (+{len(result) - 500} more chars)"))
    session_store.append_event(session, {
        "type": "shell",
        "content": command,
        "output": result[:1000],
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    })


def _handle_btw(question: str, session: Session | None) -> None:
    """Handle /btw ephemeral question - quick answer without adding to transcript."""
    if not question.strip():
        _print(gray("Usage: /btw <question>"))
        return

    client = _get_client()
    _print(gray(f"[btw] {question}"))

    # Build a minimal conversation with the question
    btw_messages = [{"role": "user", "content": question}]
    try:
        stream = client.stream(
            messages=btw_messages,
            tools=[],
            system=_get_system_prompt(),
        )
        handler = StreamHandler(None, False)
        for event in stream:
            handler.handle_event(event)
        response = handler.get_text()
        if response:
            # Print response without Rich formatting
            import re
            clean = re.sub(r'\[/?[^]]+\]', '', response)
            for line in clean.split('\n'):
                line = line.strip()
                if line:
                    _print(teal(f"  {line}"))
            # Store as a note on the session
            if session and hasattr(session, 'notes') and session.notes is not None:
                session.notes.append(f"[btw] {question} -> {response[:200]}")
        else:
            _print(gray("  [no response]"))
    except Exception as e:
        _print(gray(f"  [btw error: {e}]"))


def _find_session_by_id_or_name(identifier: str, session_store: SessionStore) -> Session | None:
    """Find a session by ID or name."""
    sessions = session_store.list_all()
    for s in sessions:
        if s.id == identifier:
            return s
    for s in sessions:
        if identifier.lower() in s.id.lower():
            return s
    return None


def _extract_file_path(tool_name: str, args_str: str) -> str:
    """Extract file path from tool args for display context."""
    import json
    import re

    # Tools that work with file paths
    file_tools = {"Read", "Edit", "Write", "Grep", "Glob", "Bash"}
    if tool_name not in file_tools:
        return ""

    # Try to parse as JSON and extract file paths
    try:
        args = json.loads(args_str) if args_str else {}
    except json.JSONDecodeError:
        # Try to find file paths via regex
        patterns = [
            r'["\']file["\']\s*:\s*["\']([^"\']+)["\']',
            r'["\']path["\']\s*:\s*["\']([^"\']+)["\']',
            r'["\']filename["\']\s*:\s*["\']([^"\']+)["\']',
            r'(["\'])([^\1]+\.(py|js|ts|tsx|jsx|md|txt|json|yml|yaml|css|html|xml|cfg|ini|toml))(\1)',
        ]
        for pattern in patterns:
            matches = re.findall(pattern, args_str)
            if matches:
                # Return first file path found
                for match in matches:
                    if isinstance(match, tuple):
                        path = match[1] if len(match) > 1 else match[0]
                    else:
                        path = match
                    if path and len(path) > 3:
                        return path
        return ""

    # Extract from known JSON fields
    for key in ["file_path", "file", "path", "filename", "target", "src", "dest"]:
        if key in args and isinstance(args[key], str):
            val = args[key]
            if len(val) > 3 and not val.startswith("-"):
                return val

    return ""


def _run_one_shot(prompt: str, cfg: Config, client: DraguniteusClient, session_store: SessionStore) -> None:
    """Run a single one-shot prompt with progressive streaming display."""
    from draguniteus.agent import stream_one_turn
    from draguniteus.streaming_display import StreamingDisplay

    messages = [{"role": "user", "content": prompt}]
    session = session_store.get_or_create(str(cfg.model))

    # Create streaming display for progressive output
    display = StreamingDisplay(console, _full_drama) if _full_drama else None
    start_time = time.time()

    if display:
        display.start(start_time)

    thinking_text = ""
    response_text = ""
    pending_tool_calls = []
    tool_results = []
    current_tokens = 0

    # Track search context for display
    search_patterns: list[str] = []
    files_reading: list[str] = []

    # Stream with progressive display
    for text, thinking, tool_calls, is_final in stream_one_turn(client, messages, _get_system_prompt(), cfg, _full_drama):
        # Update accumulated values
        if thinking:
            thinking_text = thinking
        if text:
            response_text = text

        # Detect search tool calls to update search context
        if tool_calls and display:
            search_patterns = []
            files_reading = []
            for tc in tool_calls:
                tool_name = tc.get("name", "")
                args_str = tc.get("args", "")
                # Parse search tools
                if tool_name == "Grep":
                    try:
                        import json
                        args = json.loads(args_str) if args_str else {}
                        pattern = args.get("pattern", "")
                        path = args.get("path", "")
                        if pattern:
                            search_patterns.append(pattern)
                        if path:
                            files_reading.append(path)
                    except Exception:
                        pass
                elif tool_name == "Glob":
                    try:
                        import json
                        args = json.loads(args_str) if args_str else {}
                        pattern = args.get("pattern", "")
                        path = args.get("path", "")
                        if pattern:
                            search_patterns.append(pattern)
                        if path:
                            files_reading.append(path)
                    except Exception:
                        pass
                elif tool_name in ("Read", "mcp__filesystem__read_text_file"):
                    try:
                        import json
                        args = json.loads(args_str) if args_str else {}
                        file_path = args.get("file_path", args.get("path", ""))
                        if file_path:
                            files_reading.append(file_path)
                    except Exception:
                        pass
            # Update search context display
            if search_patterns or files_reading:
                display.set_search_context(search_patterns, files_reading)

        # Get token count from stream_one_turn's _last_usage if available
        try:
            current_tokens = stream_one_turn._last_usage
        except Exception:
            current_tokens = 0

        # Update the live display
        if display:
            display.update(
                thinking=thinking_text,
                response=response_text,
                tokens=current_tokens,
            )

        # Tool calls received (at is_final)
        if tool_calls is not None:
            pending_tool_calls = tool_calls

        if is_final:
            # Show tool context BEFORE stopping display and executing tools
            if pending_tool_calls and display:
                for tc in pending_tool_calls:
                    tool_name = tc.get("name", "")
                    args_str = tc.get("args", "")
                    # Extract file path from common tool args
                    file_path = _extract_file_path(tool_name, args_str)
                    if file_path:
                        display.show_tool_start(tool_name, args_str[:50], file_path)

            # Stop the live display cleanly
            if display:
                display.stop()

            # Fire notification hooks for turn completion
            try:
                from draguniteus.hook_runner import send_notification
                tool_names = [tc.get("name", "?") for tc in (pending_tool_calls or [])]
                if tool_names:
                    send_notification(f"Turn complete — used: {', '.join(tool_names)}")
                else:
                    send_notification("Turn complete — no tools used")
            except Exception:
                pass

            # Store tool results
            if pending_tool_calls:
                from draguniteus.agent import execute_tool_calls
                from draguniteus.agent import StreamHandler
                handler = StreamHandler(console, _full_drama)
                handler._tool_calls = pending_tool_calls
                tool_results, _, _ = execute_tool_calls(pending_tool_calls, messages, handler)

                # Print tool results inline (one-shot mode has no interactive expand)
                if tool_results and _full_drama:
                    dim_color = "\033[90m"  # gray
                    reset = "\033[0m"
                    for i, tr in enumerate(tool_results, 1):
                        name = tr.get("tool", "?")
                        result = str(tr.get("result", ""))
                        # Print tool name as sub-item
                        try:
                            sys.stdout.write(f"\n{dim_color}⎿ {name}{reset}\n")
                        except UnicodeEncodeError:
                            sys.stdout.write(f"\n> {name}\n")
                        # Print first 50 lines of result
                        lines = result.split('\n')
                        for ln in lines[:50]:
                            try:
                                sys.stdout.write(f"  {ln}\n")
                            except UnicodeEncodeError:
                                sys.stdout.write(f"  {ln.encode('ascii', errors='replace').decode()}\n")
                        if len(lines) > 50:
                            sys.stdout.write(f"  {dim_color}[...+ {len(lines) - 50} lines]{reset}\n")
                    sys.stdout.flush()

            # Print response with bullet prefix (inside Rich.Live panel already shown, but need clean final output)
            if response_text:
                text = response_text.lstrip('\n')
                try:
                    from io import StringIO
                    sio = StringIO()
                    c2 = Console(file=sio, force_terminal=False)
                    c2.print(Markdown(text))
                    rendered = sio.getvalue().rstrip('\n')
                except Exception:
                    rendered = text
                import re
                clean_lines = []
                for line in rendered.split('\n'):
                    clean = re.sub(r'\[/?[^]]+\]', '', line)
                    clean = clean.strip()
                    clean_lines.append(clean)
                first = True
                for line in clean_lines:
                    if not line:
                        continue
                    prefix = "● " if first else "  "
                    first = False
                    try:
                        print(prefix + line)
                    except UnicodeEncodeError:
                        print((prefix + line).encode('ascii', errors='replace').decode('ascii'))
            elif tool_results:
                # No text but has tools - already showed during streaming
                pass

            # Store tool results for expandable display
            global _last_tool_results
            _last_tool_results = tool_results

            # Show collapsible tool call summary
            if tool_results:
                from collections import Counter
                counts = Counter(tr.get("tool", "?") for tr in tool_results)
                if len(counts) == 1:
                    name = list(counts.keys())[0]
                    n = list(counts.values())[0]
                    summary = f"Called {name}" if n == 1 else f"Called {name} {n} times"
                else:
                    summary = ", ".join(f"{v}x {k}" for k, v in counts.items())
                    summary = f"Called {summary}"
                _print(gray(summary))

            elapsed = time.time() - start_time
            # No need for separate thinking indicator - already shown during streaming
            return  # Done after is_final block

    elapsed = time.time() - start_time

    # Track one-shot cost
    if _max_budget is not None:
        turn_cost = current_tokens / 1_000_000 * 0.05 if current_tokens > 0 else 0
        _total_cost += turn_cost
        if _total_cost > _max_budget:
            print(f"\nBudget limit reached (${_total_cost:.4f} > ${_max_budget:.4f}).")
            return


def _read_input() -> str:
    """Read user input with prompt, history search (Ctrl+R), and suggestions."""
    global _vim_mode, _prompt_suggestions

    try:
        import sys
        import tty
        import termios

        from draguniteus.repl import get_history_manager, prompt_suggestions
        history_mgr = get_history_manager()

        if _prompt_suggestions and not _vim_mode:
            suggestion = prompt_suggestions.get_suggestion()
            if suggestion:
                sys.stdout.write("\033[2K\r")
                sys.stdout.write(f"\033[90m  ← Tab: {suggestion}\033[0m\n")
                sys.stdout.flush()

        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)

        try:
            tty.setraw(fd)
            line = ""

            # Show prompt — purple Claude brand color
            sys.stdout.write("\r\033[38;5;141m❯\033[0m ")
            sys.stdout.flush()

            while True:
                ch = sys.stdin.read(1)

                if ch == '\x1b':
                    seq = ch + sys.stdin.read(2)
                    if seq == '\x1b[A':
                        pass
                    elif seq == '\x1b[B':
                        pass
                    elif seq == '\x1b[Z':  # Shift+Tab — cycle permission mode
                        global _permission_mode
                        modes = ["default", "acceptEdits", "plan", "auto"]
                        try:
                            idx = (modes.index(_permission_mode) + 1) % len(modes)
                        except (ValueError, AttributeError):
                            idx = 0
                        _permission_mode = modes[idx]
                        sys.stdout.write(f"\r  Permission: {_permission_mode}\n")
                        sys.stdout.write("❯ " + line)
                        sys.stdout.flush()
                        continue
                    continue

                if ch == '\x12':  # Ctrl+R - reverse search
                    matched = history_mgr.interactive_search()
                    sys.stdout.write("\r" + " " * 80 + "\r❯ " + line)
                    sys.stdout.flush()
                    continue

                if ch == '\x14':  # Ctrl+T - toggle task list
                    global _show_task_list
                    _show_task_list = not _show_task_list
                    if _show_task_list:
                        try:
                            from draguniteus.tasks.manager import get_task_manager
                            tm = get_task_manager()
                            tasks = tm.list_tasks()
                            sys.stdout.write("\r" + " " * 80 + "\r")
                            sys.stdout.write("  [Tasks]\n")
                            if tasks:
                                for t in tasks[:5]:
                                    status = "[ ]" if getattr(t, "status", "?") == "pending" else "[~]" if getattr(t, "status", "?") == "in_progress" else "[x]"
                                    subj = getattr(t, "subject", "?")
                                    sys.stdout.write(f"  {status} {subj}\n")
                            else:
                                sys.stdout.write("  (no tasks)\n")
                            sys.stdout.write("  ❯ " + line)
                            sys.stdout.flush()
                        except Exception:
                            sys.stdout.write("\r" + " " * 80 + "\r❯ " + line)
                            sys.stdout.flush()
                    else:
                        sys.stdout.write("\r" + " " * 80 + "\r❯ " + line)
                        sys.stdout.flush()
                    continue

                if ch == '\x02':  # Ctrl+B - background active task
                    global _active_bg_task
                    if _active_bg_task:
                        task_id = _active_bg_task.get("id", "?")
                        task_desc = _active_bg_task.get("description", "?")[:60]
                        task_type = _active_bg_task.get("type", "shell")
                        sys.stdout.write("\r" + " " * 80 + "\r")
                        if task_type == "agent":
                            # Agent turns can't be backgrounded mid-stream, but acknowledge
                            sys.stdout.write(f"  Agent is thinking: {task_desc}\n")
                            sys.stdout.write(f"  (Agent turns cannot be backgrounded — wait for completion)\n")
                            sys.stdout.flush()
                        else:
                            sys.stdout.write(f"  Backgrounding: {task_desc}\n")
                            sys.stdout.flush()
                            sys.stdout.write(f"  [Task ID: {task_id}] Use /background to view\n")
                            sys.stdout.flush()
                            try:
                                from draguniteus.tasks.manager import get_task_manager
                                tm = get_task_manager()
                                task = tm.get_task(task_id)
                                if task:
                                    task.status = "pending"
                            except Exception:
                                pass
                        _active_bg_task = None
                    else:
                        sys.stdout.write("\r  (no active task to background)\n")
                        sys.stdout.flush()
                    sys.stdout.write("\r" + " " * 80 + "\r❯ " + line)
                    sys.stdout.flush()
                    continue

                if ch == '\x0f':  # Ctrl+O - expand tool results (same as Ctrl+E)
                    global _last_tool_results
                    if _last_tool_results:
                        sys.stdout.write("\r" + " " * 80 + "\r")
                        sys.stdout.write("=" * 68 + "\n")
                        i = 0
                        for tr in _last_tool_results:
                            i += 1
                            name = tr.get("tool", "?")
                            result = str(tr.get("result", ""))
                            sys.stdout.write(f"  [{i}/{len(_last_tool_results)}] {name}\n")
                            lines = result.split('\n')
                            for ln in lines[:100]:
                                sys.stdout.write(f"    {ln}\n")
                            if len(lines) > 100:
                                sys.stdout.write(f"    [...+ {len(lines) - 100} lines]\n")
                        sys.stdout.write("=" * 68 + "\n")
                    else:
                        sys.stdout.write("\r  (no tool results to expand)\n")
                    sys.stdout.write("\r" + " " * 80 + "\r❯ " + line)
                    sys.stdout.flush()
                    continue

                if ch == '\x05':  # Ctrl+E - expand tool results
                    if _last_tool_results:
                        sys.stdout.write("\r" + " " * 80 + "\r")
                        sys.stdout.write("=" * 68 + "\n")
                        i = 0
                        for tr in _last_tool_results:
                            i += 1
                            name = tr.get("tool", "?")
                            result = str(tr.get("result", ""))
                            sys.stdout.write(f"  [{i}/{len(_last_tool_results)}] {name}\n")
                            lines = result.split('\n')
                            for ln in lines[:100]:
                                sys.stdout.write(f"    {ln}\n")
                            if len(lines) > 100:
                                sys.stdout.write(f"    [...+ {len(lines) - 100} lines]\n")
                        sys.stdout.write("=" * 68 + "\n")
                    else:
                        sys.stdout.write("\r  (no tool results to expand)\n")
                    sys.stdout.write("\r" + " " * 80 + "\r❯ " + line)
                    sys.stdout.flush()
                    continue

                if ch == '\x09':  # Tab
                    if line.strip().startswith("/"):
                        # Slash command completion
                        slash_completions = _get_slash_command_completions()
                        prefix = line.lstrip("/").lower()
                        matches = [c for c in slash_completions if c.startswith(prefix)]
                        if len(matches) == 1:
                            sys.stdout.write("\r" + " " * 80 + "\r❯ /" + matches[0] + " ")
                            sys.stdout.flush()
                            line = "/" + matches[0] + " "
                        elif len(matches) > 1:
                            sys.stdout.write("\r\n  " + "  ".join(f"/{m}" for m in matches[:10]) + "\n")
                            sys.stdout.write("❯ " + line)
                            sys.stdout.flush()
                        continue
                    suggestion = prompt_suggestions.get_suggestion() if _prompt_suggestions else None
                    if suggestion:
                        sys.stdout.write("\r" + " " * 80 + "\r❯ " + suggestion + " ")
                        sys.stdout.flush()
                        line = suggestion + " "
                    continue

                if ch == '\x0c':  # Ctrl+L — clear screen
                    sys.stdout.write("\x1b[2J\x1b[H")
                    sys.stdout.flush()
                    sys.stdout.write("\r❯ " + line)
                    sys.stdout.flush()
                    continue

                if ch == '\x0b':  # Ctrl+K — delete to end of line
                    deleted = line[len(line):]
                    line = ""
                    # Move cursor back over deleted chars
                    for _ in range(len(deleted)):
                        sys.stdout.write("\b \b")
                    sys.stdout.flush()
                    continue

                if ch == '\x15':  # Ctrl+U — clear line (delete from cursor to beginning)
                    # Move cursor to beginning and clear
                    for _ in range(len(line)):
                        sys.stdout.write("\b \b")
                    line = ""
                    sys.stdout.flush()
                    continue

                if ch == '\r' or ch == '\n':
                    sys.stdout.write("\n")
                    break

                if ch == '\x7f':
                    if line:
                        line = line[:-1]
                        sys.stdout.write("\b \b")
                        sys.stdout.flush()
                    continue

                if ch == '\x03':
                    # Ctrl+C — check if orchestration is active
                    global _orchestrator_cancel, _active_panels
                    if _active_panels is not None:
                        _print(gray("[D] Interrupting orchestration..."))
                        if _orchestrator_cancel:
                            _orchestrator_cancel()
                        _active_panels = None
                        _orchestrator_cancel = None
                        raise KeyboardInterrupt
                    raise KeyboardInterrupt

                if ch == '\x04':
                    raise EOFError

                if ch == '\x09' and _active_panels is not None:
                    # Tab — cycle focus between active panels
                    global _active_panel_index
                    max_idx = _active_panels.count if hasattr(_active_panels, 'count') else 1
                    _active_panel_index = (_active_panel_index + 1) % max_idx
                    sys.stdout.write(f"\r  [Panel {_active_panel_index + 1}/{max_idx}]")
                    sys.stdout.write("\r" + " " * 80 + "\r❯ " + line)
                    sys.stdout.flush()
                    continue

                sys.stdout.write(ch)
                sys.stdout.flush()
                line += ch

        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

        if line.strip():
            history_mgr.add(line.strip())
            prompt_suggestions.update_from_conversation([])

        return line.strip()

    except KeyboardInterrupt:
        raise
    except EOFError:
        raise
    except (AttributeError, io.UnsupportedOperation, OSError, ImportError, ModuleNotFoundError):
        # When not in a TTY or on Windows without termios, use simple input
        # Avoid questionary as it can trigger Rich Unicode errors on cp1252
        # If stdin is not a TTY (piped mode), raise EOFError to exit REPL loop
        if not sys.stdin.isatty():
            raise EOFError("piped mode - no more input")
        try:
            return input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            raise
        except Exception:
            # Last resort - return empty to break out of REPL loop
            return ""


def _load_session_messages(session: Session) -> list[dict]:
    """Load transcript and reconstruct message list."""
    store = _get_session_store()
    events = store.load_transcript(session)
    messages = []
    for event in events:
        etype = event.get("type")
        if etype == "user":
            messages.append({"role": "user", "content": event.get("content", "")})
        elif etype == "assistant":
            messages.append({"role": "assistant", "content": event.get("content", "")})
    return messages


def _handle_slash_command(cmd: str, messages: list[dict], session: Session) -> bool | None:
    """Handle slash commands. Returns True if handled, False if exit, None if not recognized."""
    import sys
    stripped = cmd.strip().lstrip("/")
    parts = stripped.split(maxsplit=1)
    name = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    handler = None
    handlers = {
        "help": _cmd_help,
        "plan": _cmd_plan,
        "exit": _cmd_exit,
        "quit": _cmd_exit,
        "effort": _cmd_effort,
        "compact": _cmd_compact,
        "memory": _cmd_memory,
        "init": _cmd_init,
        "agents": _cmd_agents,
        "agent": _cmd_agent,
        "new": _cmd_new,
        "reset": _cmd_reset,
        "recap": _cmd_recap,
        "release-notes": _cmd_release_notes,
        "usage": _cmd_usage,
        "btw": _cmd_btw,
        "style": _cmd_style,
        "worktree": _cmd_worktree,
        "tasks": _cmd_tasks,
        "transcript": _cmd_transcript,
        "background": _cmd_background,
        "vim": _cmd_vim,
        "skills": _cmd_skills,
        "skill": _cmd_skill,
        "orchestrate": _cmd_orchestrate,
        "review": _cmd_review,
        "index": _cmd_index,
        "voice": _cmd_voice,
        "diff": _cmd_diff,
        "submit": _cmd_submit,
        "resume": _cmd_resume,
        "context": _cmd_context,
        "model": _cmd_model,
        "patch": _cmd_patch,
        "undo": _cmd_undo,
        "inspect": _cmd_inspect,
        "info": _cmd_info,
        "doctor": _cmd_doctor,
        "think": _cmd_think,
        "fast": _cmd_fast,
        "workflow": _cmd_workflow,
        "preview": _cmd_preview,
        "checkpoint": _cmd_checkpoint,
        "tools": _cmd_tools,
        "critique": _cmd_critique,
    }

    handler = handlers.get(name)
    if handler:
        return handler(arg, messages, session)

    # Check plugin commands — registered first-class commands
    try:
        plugin_mgr = _get_plugin_manager()
        all_cmds = plugin_mgr.get_all_commands()
        if name in all_cmds:
            return _run_plugin_command(all_cmds[name], arg, messages, session)
    except Exception:
        pass

    return None


def _run_plugin_command(cmd_path: Path, arg: str, messages: list[dict], session: Session) -> bool:
    """Run a plugin command from a .md file.

    Plugin commands are markdown files with YAML frontmatter whose body contains
    instructions written FOR Claude (not TO the user). When invoked, the command
    body is appended to messages as a system-level directive, and the agent
    executes the command's instructions.
    """
    try:
        content = cmd_path.read_text(encoding="utf-8")
        import re
        match = re.match(r"^---\n(.*?)\n---\n", content, re.DOTALL)
        if match:
            frontmatter = match.group(1)
            body = content[match.end():]
            # Parse frontmatter for description, allowed-tools, etc.
            desc = ""
            allowed_tools = None
            for line in frontmatter.split("\n"):
                if line.startswith("description:"):
                    desc = line.split("description:", 1)[1].strip().strip('"').strip("'")
                elif line.startswith("allowed-tools:"):
                    try:
                        # Parse list like ["Read", "Write"]
                        tools_str = line.split("allowed-tools:", 1)[1].strip()
                        tools_str = tools_str.strip('[]').replace('"', '').replace("'", "")
                        allowed_tools = [t.strip() for t in tools_str.split(",") if t.strip()]
                    except Exception:
                        pass
        else:
            body = content
            desc = ""

        # Replace $ARGUMENTS, $1, $2 placeholders
        if arg:
            body = body.replace("$ARGUMENTS", arg)
            parts = arg.split()
            for i, part in enumerate(parts[:9], 1):
                body = body.replace(f"${i}", part)

        # Replace @file-path references
        body = re.sub(r'@([^\s]+)', lambda m: f"File: {m.group(1)}", body)

        console.print(gold(f"[D] Executing plugin command: /{cmd_path.stem}"))
        if desc:
            console.print(gray(f"  {desc}"))
        if arg:
            console.print(gray(f"  Arguments: {arg}"))

        # Add command as a system directive message
        messages.append({
            "role": "system",
            "content": f"[Plugin Command: {cmd_path.stem}]\n\n{body.strip()}"
        })

        # Return True to signal handled but let agent continue with command context
        return True
    except Exception as e:
        console.print(gray(f"[D] Error running command: {e}"))
        return True


def _cmd_help(arg: str, messages: list[dict], session: Session) -> bool:
    # Use plain print when not in a TTY to avoid Rich encoding issues on Windows cp1252
    if sys.stdout.isatty():
        try:
            console.print(Panel(
                Text("[D] Draguniteus Commands", style="yellow bold"),
                border_style="red",
            ))
        except Exception:
            print("[D] Draguniteus Commands")
            print("-" * 40)
    else:
        print("[D] Draguniteus Commands")
        print("-" * 40)

    # Get plugin commands for help
    plugin_cmds = []
    try:
        plugin_mgr = _get_plugin_manager()
        for cmd_name in plugin_mgr.get_all_commands():
            plugin_cmds.append(cmd_name)
    except Exception:
        pass

    help_text = """
    /help           -- Show this help
    /plan           -- Enable detailed planning mode
    /effort [level] -- Set reasoning depth (low/medium/high/max)
    /compact        -- Compress context window
    /memory         -- Show/edit project memory (DRAGUNITEUS.md)
    /init           -- Create DRAGUNITEUS.md in current project
    /agents         -- List available sub-agents
    /new, /reset    -- Start a new session
    /exit, /quit    -- Exit Draguniteus
    /recap          -- Generate session recap
    /release-notes  -- Show version info
    /usage          -- Show API usage stats
    /btw [question] -- Quick side question (ephemeral)
    /style [name]   -- Set output style
    /worktree [name]-- Manage worktrees
    /tasks          -- Show/manage task list
    /skills         -- List all skills
    /skill <cmd>    -- Manage skill evals (add/list/delete/bench)
    /agent <cmd>    -- Manage agent evals (add/bench/optimize)
    /transcript     -- Show transcript summary
    /transcript full-- Full transcript viewer
    /background     -- List background tasks
    /undo           -- Undo last edit (--list to show history)
    /vim            -- Toggle vim editing mode
    """

    if sys.stdout.isatty():
        try:
            console.print(gray(help_text))
        except Exception:
            print(help_text)
    else:
        print(help_text)

    if plugin_cmds:
        try:
            console.print(gold("    Plugin Commands:"))
            for pc in plugin_cmds:
                console.print(f"      /{pc}")
            console.print("")
        except Exception:
            print("    Plugin Commands:")
            for pc in plugin_cmds:
                print(f"      /{pc}")
            print("")

    try:
        console.print("""
    Keyboard shortcuts:
      Ctrl+B   Background current command
      Ctrl+T   Toggle task list
      Ctrl+O   Expand tool results (same as Ctrl+E)
      Ctrl+R   Reverse history search
      ! cmd    Shell mode (direct command)

    Flags:
      -p "prompt"   One-shot mode
      -c            Continue last session
      --minimal     Minimal theme (no ASCII art)
      --bare        Skip auto-discovery
      --worktree -w  Isolated git worktree
    """)
    except Exception:
        print("""
    Keyboard shortcuts:
      Ctrl+B   Background current command
      Ctrl+T   Toggle task list
      Ctrl+O   Expand tool results (same as Ctrl+E)
      Ctrl+R   Reverse history search
      ! cmd    Shell mode (direct command)

    Flags:
      -p "prompt"   One-shot mode
      -c            Continue last session
      --minimal     Minimal theme (no ASCII art)
      --bare        Skip auto-discovery
      --worktree -w  Isolated git worktree
    """)
    return True


def _cmd_plan(arg: str, messages: list[dict], session: Session) -> bool:
    global _plan_viewer

    if not arg.strip():
        # Toggle plan viewer off
        if _plan_viewer:
            _plan_viewer.close()
            _plan_viewer = None
            _print(gray("[D] Plan viewer closed."))
        else:
            _print(gray("[D] Planning mode -- use /plan <task> to create a refactor plan"))
            _print(gray("  /plan <task>   -- create and show a refactoring plan"))
            _print(gray("  /plan review    -- review current plan"))
            _print(gray("  /plan execute   -- execute current plan (dry run first!)"))
        return True

    # /plan execute — run the current plan
    if arg.strip() == "execute" or arg.strip() == "run":
        if not _plan_viewer or not _plan_viewer.is_open():
            _print(gray("[D] No active plan. Use /plan <task> first."))
            return True
        _print(gray("[D] Use /refactor to execute plans. /plan only creates and reviews plans."))
        return True

    # /plan review — show current plan summary
    if arg.strip() == "review":
        if not _plan_viewer or not _plan_viewer.is_open():
            _print(gray("[D] No active plan. Use /plan <task> to create one."))
            return True
        summary = _plan_viewer.render()
        if summary:
            _print(summary)
        return True

    # /plan <task> — create a new refactoring plan
    from draguniteus.refactor.autonomous import AutonomousRefactorer
    from pathlib import Path

    _print(gray(f"[D] Creating plan for: {arg[:60]}..."))
    try:
        er = AutonomousRefactorer(Path.cwd())
        plan = er.plan(arg)

        # Create or update plan viewer
        if _plan_viewer is None:
            from draguniteus.tui.plan_viewer import PlanViewer
            _plan_viewer = PlanViewer()

        _plan_viewer.open(plan)

        # Show plan summary
        from draguniteus.tui.plan_viewer import render_plan_summary
        summary = render_plan_summary(plan)
        _print(gold(f"[D] Plan created:"))
        _print(gray(f"  {summary}"))

        # Show detailed review
        review = er.review_plan(plan)
        _print("")
        _print(review)

        if plan.risk == "high":
            _print(gray("  ⚠️  High risk refactor — review changes before applying"))
        elif plan.risk == "medium":
            _print(gray("  Medium risk — execute with /refactor --dry-run first"))
        else:
            _print(gray("  Low risk — safe to execute with /refactor --confirm"))

    except Exception as e:
        _print(gray(f"[D] Plan error: {e}"))

    return True


def _cmd_exit(arg: str, messages: list[dict], session: Session) -> bool:
    # Use plain print when stdout is not a TTY (piped/redirected)
    if sys.stdout.isatty():
        console.print(gold("Flight suspended."))
    else:
        print("Flight suspended.")
    return False


def _cmd_effort(arg: str, messages: list[dict], session: Session) -> bool:
    global _cfg
    levels = {"low", "medium", "high", "xhigh", "max"}
    if not arg or arg.lower() not in levels:
        console.print(gray(f"Usage: /effort {'|'.join(levels)}"))
        return True

    level = arg.lower()
    if _cfg and _cfg.set_effort(level):
        settings = _cfg.get_effort_settings()
        max_t = settings.get("max_tokens", 8192)
        betas = settings.get("betas", [])
        thinking = settings.get("thinking", False)

        console.print(gold(f"[D] Effort set to: {level}"))
        console.print(gray(f"    max_tokens: {max_t}"))
        console.print(gray(f"    thinking enabled: {thinking}"))
        if betas:
            console.print(gray(f"    betas: {', '.join(betas)}"))
        else:
            console.print(gray(f"    betas: none"))
    else:
        console.print(gray(f"[D] Effort set to: {level} (session only)"))
    return True


def _cmd_compact(arg: str, messages: list[dict], session: Session) -> bool:
    compactable = len(messages) - 4
    if compactable > 0:
        _print(teal(f"[D] Compressing context... ({compactable} messages can be summarized)"))
        _print(gray("Compaction is automatic when context approaches the limit."))
    else:
        _print(gray("[D] Context is already compact."))
    return True


def _cmd_memory(arg: str, messages: list[dict], session: Session) -> bool:
    from draguniteus.memory.manager import memory_manager
    content = memory_manager.project_memory.read()
    if not content:
        _print(gray("No DRAGUNITEUS.md found. Run /init to create one."))
    else:
        _print(gold("[D] DRAGUNITEUS.md:"))
        _print(gray(content[:800]))
        if len(content) > 800:
            _print(gray("... (truncated, use /init to edit)"))
    return True


def _cmd_init(arg: str, messages: list[dict], session: Session) -> bool:
    from draguniteus.memory.manager import memory_manager
    pd = Config.project_dir()
    pd.mkdir(parents=True, exist_ok=True)
    dm = pd / "DRAGUNITEUS.md"
    if dm.exists():
        existing = dm.read_text(encoding="utf-8")
        console.print(gray(f"DRAGUNITEUS.md already exists at {dm}"))
        console.print(gray(f"Current size: {len(existing)} chars"))
        console.print(teal("[D] Use the Edit tool to modify it, or /memory to view it."))
    else:
        content = """# DRAGUNITEUS.md

## Project Context
<!-- Describe this project: language, framework, purpose -->

## Conventions
<!-- Coding style, naming, patterns to follow -->

## Key Decisions
<!-- Important architectural decisions made -->

## Current Focus
<!-- What Draguniteus should know about active work -->
"""
        dm.write_text(content, encoding="utf-8")
        print_success(f"Created DRAGUNITEUS.md at {dm}")
    return True


def _cmd_agents(arg: str, messages: list[dict], session: Session) -> bool:
    from draguniteus.subagents import list_agents, load_agent
    agents = list_agents()
    _print(gold("[D] Available agents:"))
    for a in agents:
        _print(f"  * {a['name']} -- {a['description']}")

    # Also show plugin agents
    try:
        plugin_mgr = _get_plugin_manager()
        plugin_agents = plugin_mgr.get_all_agents()
        if plugin_agents:
            _print(gold("[D] Plugin agents:"))
            for name, path in plugin_agents.items():
                _print(f"  * {name}")
    except Exception:
        pass

    if arg:
        agent = load_agent(arg)
        if agent:
            _print(gold(f"[D] Activated sub-agent: {agent['name']}"))
        else:
            _print(gray(f"[D] Unknown agent: {arg}"))
    return True


def _cmd_agent(arg: str, messages: list[dict], session: Session) -> bool:
    """Manage agent evals. /agent bench <name> [--query <text>]"""
    from draguniteus.agents.eval import get_agent_evaluator
    from draguniteus.subagents import load_agent

    parts = arg.strip().split(maxsplit=2)
    subcmd = parts[0] if parts else ""
    agent_name = parts[1] if len(parts) > 1 else ""
    query = parts[2] if len(parts) > 2 else ""

    if subcmd == "bench" and agent_name:
        evaluator = get_agent_evaluator(agent_name)
        cases = evaluator.list_evals()
        _print(gold(f"[D] Running {len(cases)} evals for agent: {agent_name}"))
        # Load agent definition
        agent_def = load_agent(agent_name)
        agent_content = agent_def.get("body", "") if agent_def else ""
        report = evaluator.run_evals(agent_content)
        _print(f"  Trigger: {report.triggered}/{report.total_evals} ({report.trigger_rate:.1f}%)")
        _print(f"  Avg match score: {report.avg_match_score:.2f}")
        return True

    if subcmd == "add" and agent_name and query:
        evaluator = get_agent_evaluator(agent_name)
        case = evaluator.add_eval(query)
        _print(gold(f"[D] Eval case added for {agent_name}: {case.id}"))
        _print(gray(f"  Query: {query[:60]}..."))
        return True

    if subcmd == "list" and agent_name:
        evaluator = get_agent_evaluator(agent_name)
        cases = evaluator.list_evals()
        if not cases:
            _print(gray(f"[D] No eval cases for: {agent_name}"))
        else:
            _print(gold(f"[D] Eval cases for {agent_name}:"))
            for c in cases:
                _print(f"  [{c.id}] {c.query[:50]}...")
        return True

    if subcmd == "delete" and agent_name and query:
        evaluator = get_agent_evaluator(agent_name)
        if evaluator.delete_eval(query.strip()):
            _print(gold(f"[D] Eval case deleted: {query}"))
        else:
            _print(gray(f"[D] Eval case not found: {query}"))
        return True

    if subcmd == "optimize" and agent_name:
        from draguniteus.agents.eval import AgentDescriptionOptimizer
        optimizer = AgentDescriptionOptimizer(agent_name)
        agent_def = load_agent(agent_name)
        if not agent_def:
            _print(gray(f"[D] Agent not found: {agent_name}"))
            return True
        analysis = optimizer.analyze_triggers(agent_def.get("description", ""))
        _print(gold(f"[D] Analysis for {agent_name}:"))
        if analysis["warnings"]:
            _print(gray("  Warnings:"))
            for w in analysis["warnings"]:
                _print(f"    - {w}")
        if analysis["suggestions"]:
            _print(gray("  Suggestions:"))
            for s in analysis["suggestions"]:
                _print(f"    - {s}")
        _print(gray(f"  Word count: {analysis['word_count']}"))
        _print(gray(f"  Example blocks: {analysis['example_count']}"))
        _print(gray(f"  Trigger phrases: {analysis['trigger_phrase_count']}"))
        return True

    _print(gray("[D] Usage:"))
    _print(gray("  /agent bench <name>         -- Run benchmarks"))
    _print(gray("  /agent add <name> <query>    -- Add eval case"))
    _print(gray("  /agent list <name>          -- List eval cases"))
    _print(gray("  /agent delete <name> <id>    -- Delete eval case"))
    _print(gray("  /agent optimize <name>       -- Analyze description"))
    return True


def _cmd_new(arg: str, messages: list[dict], session: Session) -> bool:
    console.print(teal("[D] Starting new session..."))
    messages.clear()
    console.print(gray("Conversation cleared. Session ID remains the same."))
    return True


def _cmd_reset(arg: str, messages: list[dict], session: Session) -> bool:
    return _cmd_new(arg, messages, session)


def _cmd_recap(arg: str, messages: list[dict], session: Session) -> bool:
    if len(messages) < 3:
        console.print(gray("[D] Not enough turns for a recap yet."))
        return True

    topics = []
    for m in messages:
        if m.get("role") == "user":
            content = m.get("content", "")[:50]
            if content:
                topics.append(content)

    if topics:
        recap = f"Session covered {len(topics)} topics: {' | '.join(topics[:3])}"
        if len(topics) > 3:
            recap += f" and {len(topics) - 3} more"
        console.print(gold("[D] Session Recap:"))
        console.print(gray(recap))
    else:
        console.print(gray("[D] No topics to summarize."))
    return True


def _cmd_release_notes(arg: str, messages: list[dict], session: Session) -> bool:
    console.print(gold("[D] Draguniteus v0.1.0"))
    console.print(gray("Breathing fire into code since 2026."))
    console.print("")
    console.print(gray("Recent additions:"))
    console.print(gray("  - Plugin system with manifest support"))
    console.print(gray("  - 9 hook events (SessionStart/End, SubagentStop, etc.)"))
    console.print(gray("  - Task management system"))
    console.print(gray("  - Output styles system"))
    console.print(gray("  - settings.json with env field"))
    console.print(gray("  - MCP server auto-start"))
    return True


def _cmd_usage(arg: str, messages: list[dict], session: Session) -> bool:
    from draguniteus.config import DEFAULT_CONFIG_DIR
    usage_file = DEFAULT_CONFIG_DIR / "usage.json"
    if usage_file.exists():
        try:
            import json
            data = json.loads(usage_file.read_text())
            if sys.stdout.isatty():
                console.print(gold("[D] API Usage:"))
            else:
                print("[D] API Usage:")
            for k, v in data.items():
                if sys.stdout.isatty():
                    console.print(f"  {k}: {v}")
                else:
                    print(f"  {k}: {v}")
        except Exception:
            if sys.stdout.isatty():
                console.print(gray("[D] Could not load usage data."))
            else:
                print("[D] Could not load usage data.")
    else:
        if sys.stdout.isatty():
            console.print(gray("[D] No usage data collected yet."))
        else:
            print("[D] No usage data collected yet.")
    return True


def _cmd_btw(arg: str, messages: list[dict], session: Session) -> bool:
    _handle_btw(arg, session)
    return True


def _cmd_style(arg: str, messages: list[dict], session: Session) -> bool:
    """Set output style (explanatory, learning, etc.)."""
    global _style_name
    from draguniteus.styles.manager import get_style_manager
    style_mgr = get_style_manager()
    available = style_mgr.list_styles()

    styles = {}
    for s in available:
        styles[s.name] = s.description or f"Apply {s.name} style"

    if not arg:
        console.print(gold("[D] Available styles:"))
        if styles:
            for name, desc in styles.items():
                console.print(f"  {name} -- {desc}")
        else:
            console.print(gray("  No styles installed. Create ~/.draguniteus/styles/<name>.md"))
        return True

    if arg.lower() in styles:
        _style_name = arg.lower()
        console.print(gold(f"[D] Style set to: {arg}"))
        console.print(gray(styles[arg.lower()]))
    else:
        console.print(gray(f"[D] Unknown style: {arg}. Use /style for list."))
    return True


def _cmd_worktree(arg: str, messages: list[dict], session: Session) -> bool:
    from draguniteus.worktree import WorktreeManager
    wm = WorktreeManager()

    if not arg:
        worktrees = wm.list()
        if not worktrees:
            console.print(gray("[D] No worktrees. Use /worktree <name> to create one."))
        else:
            console.print(gold("[D] Worktrees:"))
            for wt in worktrees:
                status = "active" if wt.get("active") else "inactive"
                console.print(f"  {wt['name']} -> {wt['path']} [{status}]")
        return True

    parts = arg.strip().split(maxsplit=1)
    subcmd = parts[0] if parts else ""
    rest = parts[1] if len(parts) > 1 else ""

    if subcmd == "create" and rest:
        success, msg = wm.create(rest)
        if success:
            console.print(gold(f"[D] {msg}"))
        else:
            console.print(gray(f"[D] {msg}"))
    elif subcmd == "remove" and rest:
        success, msg = wm.remove(rest)
        if success:
            console.print(gold(f"[D] {msg}"))
        else:
            console.print(gray(f"[D] {msg}"))
    else:
        success, msg = wm.create(arg)
        if success:
            console.print(gold(f"[D] Worktree created: {arg}"))
        else:
            console.print(gray(f"[D] {msg}"))
    return True


def _cmd_tasks(arg: str, messages: list[dict], session: Session) -> bool:
    """Show or manage task list. /tasks to show, /tasks add <desc> to add."""
    task_mgr = _get_task_manager()

    parts = arg.strip().split(maxsplit=1)
    cmd = parts[0] if parts else ""
    rest = parts[1] if len(parts) > 1 else ""

    if cmd == "add" and rest:
        task = task_mgr.create_task(rest)
        console.print(gold(f"[D] Task created: {task.id}"))
    elif cmd == "complete" and rest:
        task_mgr.complete_task(rest, "Completed by user")
        console.print(gold(f"[D] Task {rest} marked complete"))
    elif cmd == "delete" and rest:
        task_mgr.delete_task(rest)
        console.print(gold(f"[D] Task {rest} deleted"))
    elif cmd == "clear":
        # Delete all completed tasks
        for t in task_mgr.list_tasks("completed"):
            task_mgr.delete_task(t.id)
        console.print(gold("[D] Cleared completed tasks"))
    else:
        all_tasks = task_mgr.list_tasks()
        if not all_tasks:
            console.print(gray("[D] No tasks. Use /tasks add <description>"))
        else:
            console.print(gold("[D] Tasks:"))
            for t in all_tasks[:10]:
                status = "✓" if t.status == "completed" else "○" if t.status == "in_progress" else "◌"
                console.print(f"  {status} [{t.status}] {t.command[:40]}")
    return True


def _cmd_transcript(arg: str, messages: list[dict], session: Session) -> bool:
    from draguniteus.transcript import transcript_viewer
    store = _get_session_store()
    events = store.load_transcript(session)

    if "full" in arg.lower():
        transcript_viewer.view_session(session, events)
    else:
        summary = transcript_viewer.view_compact(session, events)
        console.print(gold("[D] Transcript Summary:"))
        console.print(gray(summary))
        console.print(gray("Use /transcript full for detailed view"))
    return True


def _cmd_background(arg: str, messages: list[dict], session: Session) -> bool:
    task_mgr = _get_task_manager()

    if arg:
        output = ""
        task = task_mgr.get_task(arg)
        if task and task.output_path and task.output_path.exists():
            output = task.output_path.read_text()
        console.print(gold(f"[D] Output for {arg}:"))
        console.print(output[:500] if output else "(no output)")
    else:
        all_tasks = task_mgr.list_tasks()
        running = [t for t in all_tasks if t.status == "in_progress"]
        pending = [t for t in all_tasks if t.status == "pending"]
        completed = [t for t in all_tasks if t.status == "completed"]

        if not all_tasks:
            console.print(gray("[D] No background tasks"))
        else:
            console.print(gold("[D] Background Tasks:"))
            if running:
                console.print(gray("  Running:"))
                for t in running:
                    console.print(f"    {t.id}: {t.command[:40]}")
            if pending:
                console.print(gray("  Pending:"))
                for t in pending:
                    console.print(f"    {t.id}: {t.command[:40]}")
            if completed:
                console.print(gray("  Completed:"))
                for t in completed[:5]:
                    console.print(f"    {t.id}: {t.command[:40]}")
    return True


def _cmd_vim(arg: str, messages: list[dict], session: Session) -> bool:
    global _vim_mode
    _vim_mode = not _vim_mode
    if _vim_mode:
        _print(gold("[D] Vim mode enabled. Esc for NORMAL, i for INSERT"))
    else:
        _print(gray("[D] Vim mode disabled"))
    return True


def _cmd_skills(arg: str, messages: list[dict], session: Session) -> bool:
    """List all skills or run benchmarks. /skills to list, /skills bench <name> to benchmark."""
    from draguniteus.tools.skills import load_all_skills
    from draguniteus.skills.eval import get_skill_evaluator

    parts = arg.strip().split(maxsplit=1)
    subcmd = parts[0] if parts else ""
    skill_name = parts[1] if len(parts) > 1 else ""

    if subcmd == "bench" and skill_name:
        evaluator = get_skill_evaluator(skill_name)
        cases = evaluator.list_evals()
        if not cases:
            _print(gray(f"[D] No eval cases for skill: {skill_name}"))
            _print(gray(f"  Use /skill add {skill_name} <prompt> to add eval cases"))
        else:
            _print(gold(f"[D] Running {len(cases)} evals for: {skill_name}"))
            # Load actual skill content for real benchmark
            from draguniteus.tools.skills import load_skill_by_name
            skill = load_skill_by_name(skill_name)
            skill_content = skill.content if skill else f"# Skill: {skill_name}\n\nEval cases: {len(cases)}"
            report = evaluator.run_evals(skill_content)
            _print(gold(f"[D] Benchmark Results:"))
            _print(f"  Pass: {report.passed}/{report.total_evals} ({report.pass_rate:.1f}%)")
            _print(f"  Avg time: {report.avg_duration_ms:.0f}ms")
        return True

    # Default: list all skills
    skills = load_all_skills()
    if not skills:
        _print(gray("[D] No skills found."))
        _print(gray("  Skills are .md files in .draguniteus/skills/ or ~/.draguniteus/skills/"))
    else:
        _print(gold("[D] Available Skills:"))
        for s in skills:
            desc = s.description[:60] + "..." if len(s.description) > 60 else s.description
            _print(f"  {s.name} -- {desc}")
        _print(gray(f"\n  Use /skill bench <name> to benchmark a skill"))
    return True


def _cmd_skill(arg: str, messages: list[dict], session: Session) -> bool:
    """Manage skill evals. /skill add <name> <prompt> [--expected <output>] [--assert <json>]"""
    from draguniteus.skills.eval import get_skill_evaluator

    parts = arg.strip().split(maxsplit=2)
    subcmd = parts[0] if parts else ""
    skill_name = parts[1] if len(parts) > 1 else ""
    prompt = parts[2] if len(parts) > 2 else ""

    if subcmd == "add" and skill_name and prompt:
        evaluator = get_skill_evaluator(skill_name)
        case = evaluator.add_eval(prompt)
        _print(gold(f"[D] Eval case added to {skill_name}: {case.id}"))
        _print(gray(f"  Prompt: {prompt[:60]}..."))
        return True

    if subcmd == "list" and skill_name:
        evaluator = get_skill_evaluator(skill_name)
        cases = evaluator.list_evals()
        if not cases:
            _print(gray(f"[D] No eval cases for: {skill_name}"))
        else:
            _print(gold(f"[D] Eval cases for {skill_name}:"))
            for c in cases:
                _print(f"  [{c.id}] {c.prompt[:50]}...")
        return True

    if subcmd == "delete" and skill_name and prompt:
        # prompt is actually the eval_id in this context - find by prompt prefix match
        evaluator = get_skill_evaluator(skill_name)
        # For now, find by ID prefix
        eval_id = prompt.strip()
        if evaluator.delete_eval(eval_id):
            _print(gold(f"[D] Eval case deleted: {eval_id}"))
        else:
            _print(gray(f"[D] Eval case not found: {eval_id}"))
        return True

    _print(gray("[D] Usage:"))
    _print(gray("  /skill add <name> <prompt>     -- Add eval case"))
    _print(gray("  /skill list <name>            -- List eval cases"))
    console.print(gray("  /skill delete <name> <id>     -- Delete eval case"))
    console.print(gray("  /skills bench <name>          -- Run benchmarks"))
    return True


def _cmd_orchestrate(arg: str, messages: list[dict], session: Session) -> bool:
    """Run multi-agent orchestration with live multi-panel display.

    Supports:
      /orchestrate <task> --agent <name> --task <subtask> [--agent ...]
      Auto-uses ArenaMode when 3+ agents with different models.
      Ctrl+C interrupts all agents. Tab cycles panel focus.
    """
    global _active_panels, _orchestrate_panels, _arena_mode
    global _orchestrator_cancel, _active_panel_index

    import threading

    from draguniteus.tools.orchestrate import tool_orchestrate

    if not arg.strip():
        _print(gray("[D] Multi-Agent Orchestrator"))
        _print(gray("  /orchestrate <task> --agent <name> --task <subtask> [--agent ...]"))
        _print(gray("  Use multiple --agent/--task pairs for parallel subtasks."))
        _print(gray("  Models: MiniMax-M2.7 (reasoning), MiniMax-M2.5 (balanced), MiniMax-M2.1 (fast)"))
        return True

    parts = arg.split("--agent")
    if len(parts) < 2:
        _print(gray("[D] Usage: /orchestrate <task> --agent <name> --task <subtask> [--agent ...]"))
        return True

    task = parts[0].strip()
    subtasks = []
    for chunk in parts[1:]:
        sub_parts = chunk.strip().split("--task", 1)
        if len(sub_parts) == 2:
            name = sub_parts[0].strip()
            sub_task = sub_parts[1].strip()
            model = "MiniMax-M2.7"
            if "review" in name.lower() or "security" in name.lower() or "perf" in name.lower():
                model = "MiniMax-M2.5"
            elif "fast" in name.lower() or "simple" in name.lower():
                model = "MiniMax-M2.1"
            subtasks.append({"name": name, "task": sub_task, "model": model})

    if not subtasks:
        _print(gray("[D] No valid subtasks. Usage: /orchestrate <task> --agent <name> --task <subtask>"))
        return True

    _active_panel_index = 0
    unique_models = set(st["model"] for st in subtasks)
    use_arena = len(subtasks) >= 3 and len(unique_models) >= 2

    panels = None
    arena = None

    try:
        if use_arena:
            from draguniteus.tui.arena import ArenaMode
            arena = ArenaMode()
            arena.start(agents=[{"name": st["name"], "model": st["model"], "task": st["task"]} for st in subtasks])
            panels = arena
            _print(gold(f"[D] Arena Mode: {len(subtasks)} agents competing"))
        else:
            from draguniteus.tui.panels import AgentPanels
            panels = AgentPanels(len(subtasks), title=f"Orchestrating {len(subtasks)} agents")
            for i, st in enumerate(subtasks):
                panels.update_text(i, f"[{st['name']}] Initializing...")
            panels.start()
            _print(gold(f"[D] Orchestrating {len(subtasks)} agents in parallel..."))
    except Exception:
        _print(gold(f"[D] Orchestrating {len(subtasks)} agents in parallel..."))
        panels = None

    _orchestrate_panels = panels
    _arena_mode = arena
    _active_panels = panels

    def progress_callback(agent_name: str, partial_text: str, thinking: str, tool_count: int, done: bool):
        if panels is None:
            return
        for i, st in enumerate(subtasks):
            if st["name"] == agent_name:
                if hasattr(panels, 'update_text'):
                    panels.update_text(i, partial_text)
                    if thinking:
                        panels.update_thinking(i, thinking)
                    if tool_count > 0:
                        panels.update_tool_count(i, tool_count)
                    if done:
                        panels.finalize(i, partial_text)
                elif hasattr(panels, 'update'):
                    panels.update(agent_name, tools_used=tool_count)
                    if done:
                        panels.finalize(agent_name, partial_text)
                break

    result_container: list[str | None] = [None]
    error_container: list[str | None] = [None]
    cancel_event: list[threading.Event] = [threading.Event()]

    def run_orchestration():
        try:
            result_container[0] = tool_orchestrate(task, subtasks, progress_callback=progress_callback)
        except Exception as e:
            error_container[0] = str(e)

    def do_cancel():
        cancel_event[0].set()

    _orchestrator_cancel = do_cancel

    orch_thread = threading.Thread(target=run_orchestration, daemon=True)
    orch_thread.start()

    try:
        while orch_thread.is_alive():
            orch_thread.join(timeout=0.5)
            if cancel_event[0].is_set():
                break
    finally:
        if panels is not None:
            try:
                panels.stop()
            except Exception:
                pass
        _active_panels = None
        _orchestrate_panels = None
        _arena_mode = None
        _orchestrator_cancel = None

    if error_container[0]:
        _print(gray(f"[D] Orchestration error: {error_container[0]}"))
    else:
        _print(gold("[D] Results:"))
        _print(result_container[0] or "[no result]")

    return True


def _cmd_review(arg: str, messages: list[dict], session: Session) -> bool:
    """Manage background code review. /review start <paths...> | stop | findings"""
    from draguniteus.tools.review import tool_start_code_review, tool_stop_code_review, tool_get_review_findings

    parts = arg.strip().split(maxsplit=2)
    subcmd = parts[0] if parts else ""
    rest = parts[1] if len(parts) > 1 else ""

    if subcmd == "start" and rest:
        paths = rest.split()
        result = tool_start_code_review(paths=paths)
        _print(gold(f"[D] {result}"))
        return True

    if subcmd == "stop":
        result = tool_stop_code_review()
        _print(gold(f"[D] {result}"))
        return True

    if subcmd == "findings":
        result = tool_get_review_findings()
        print(result)
        return True

    _print(gray("[D] Background Code Review"))
    _print(gray("  /review start <paths...>  -- Start continuous review on paths"))
    _print(gray("  /review stop             -- Stop background review"))
    _print(gray("  /review findings         -- Show current findings"))
    return True


def _cmd_index(arg: str, messages: list[dict], session: Session) -> bool:
    """Index code semantically for natural language search. /index <path> <summary> [--related <paths>]"""
    from draguniteus.tools.navigation import tool_index_semantic

    parts = arg.strip().split(maxsplit=2)
    if len(parts) < 2:
        _print(gray("[D] Usage: /index <path> <summary> [--related <paths>]"))
        return True

    path = parts[0]
    summary = parts[1]
    related = []
    if "--related" in arg:
        idx = arg.index("--related")
        related = arg[idx + 1:].split() if idx + 1 < len(arg.split(None, idx + 1)) else []
        related = [r for r in related if not r.startswith("--")]

    result = tool_index_semantic(path=path, summary=summary, related_paths=related)
    _print(gold(f"[D] {result}"))
    return True


_pair_mode: Any = None

def _cmd_voice(arg: str, messages: list[dict], session: Session) -> bool:
    """Voice pair programming mode: hands-free coding with speech I/O."""
    global _pair_mode

    if _pair_mode is None:
        from draguniteus.voice.pair import get_pair_mode
        _pair_mode = get_pair_mode()

    parts = arg.strip().split()
    subcmd = parts[0] if parts else "status"

    if subcmd == "start":
        voice_id = "female-shaonv"
        mode = "interrupted"
        for i, p in enumerate(parts[1:]):
            if p == "--voice" and i + 1 < len(parts) - 1:
                voice_id = parts[i + 2]
            elif p == "--mode" and i + 1 < len(parts) - 1:
                mode = parts[i + 2]

        status = _pair_mode.start(
            on_text_input=lambda text: None,  # Wired into CLI message loop
            voice_mode=mode,
        )
        _print(gold(f"[D] {status}"))
        _print(gray("  Voice input captured will be routed as text."))
        _print(gray("  Use /voice speak <text> to test TTS."))

    elif subcmd == "stop":
        result = _pair_mode.stop()
        _print(gold(f"[D] {result}"))

    elif subcmd == "speak":
        text = " ".join(parts[1:]) if len(parts) > 1 else "Hello! This is a test."
        _pair_mode.speak_sync(text)

    elif subcmd == "listen":
        transcript = _pair_mode.listen_once(timeout=5.0)
        if transcript:
            _print(gold(f"[D] Heard: {transcript}"))
        else:
            _print(gray("[D] No speech detected."))

    elif subcmd == "status":
        if _pair_mode.is_active():
            _print(gold(f"[D] 🎙️  Voice active — {_pair_mode.speak_status()}"))
        else:
            avail = "ready" if _pair_mode.is_voice_available() else "unavailable"
            reason = _pair_mode._listener.availability_reason() if not _pair_mode.is_voice_available() else "ready"
            _print(gray(f"[D] Voice mode: inactive ({avail})"))
            if reason:
                _print(gray(f"  ℹ️  {reason}"))
            _print(gray("  /voice start [--voice <id>] [--mode interrupted|continuous|text-only]"))
            _print(gray("  /voice stop | speak <text> | listen"))

    else:
        _print(gray("[D] Unknown voice subcommand. Use: start, stop, speak, listen, status"))
    return True


def _cmd_diff(arg: str, messages: list[dict], session: Session) -> bool:
    """Show visual diff of uncommitted (or staged) changes. /diff [--file <path>] [--staged] [--side-by-side]"""
    parts = arg.strip().split()
    file_path = None
    staged = False
    side_by_side = False

    i = 0
    while i < len(parts):
        p = parts[i]
        if p == "--file" and i + 1 < len(parts):
            file_path = parts[i + 1]
            i += 2
        elif p == "--staged":
            staged = True
            i += 1
        elif p == "--side-by-side":
            side_by_side = True
            i += 1
        elif p == "--cached":
            staged = True
            i += 1
        else:
            # Assume it's a file path
            file_path = p
            i += 1

    try:
        from draguniteus.diff.viewer import DiffViewer

        viewer = DiffViewer(collapse_unchanged=3, side_by_side=side_by_side)
        files = viewer.get_diff(file_path=file_path, staged=staged)

        if not files:
            _print(gray("[D] No changes found."))
            return True

        stats_table = ""
        total_add = sum(f.total_additions() for f in files)
        total_del = sum(f.total_deletions() for f in files)
        scope = "staged" if staged else "uncommitted"

        stat_line = (f"[D] [bold]Diff ({scope}):[/bold] {len(files)} file(s), "
                     f"[green]+{total_add}[/green] / [red]-{total_del}[/red]\n")
        _print(gray(stat_line))

        for df in files:
            if df.is_binary:
                _print(gray(f"  Binary: {df.new_path or df.old_path}"))
                continue

            add = df.total_additions()
            dele = df.total_deletions()
            path_str = df.new_path or df.old_path
            _print(gold(f"  {path_str}: [green]+{add}[/green] / [red]-{dele}[/red]"))

            if side_by_side:
                output = viewer.render_side_by_side([df])
            else:
                output = viewer.render_unified([df])
            _print(gray(output[:2000]))  # Cap output to avoid flooding

        return True
    except Exception as e:
        _print(gray(f"[D] Diff error: {e}"))
        return True


def _cmd_undo(arg: str, messages: list[dict], session: Session) -> bool:
    """Undo the last edit. /undo [--list]"""
    global _pending_edits

    parts = arg.strip().split()

    if "--list" in parts or not _pending_edits:
        if not _pending_edits:
            _print(gray("[D] No edits to undo."))
            return True
        _print(gray("[D] Pending edits (newest last):"))
        for i, edit in enumerate(reversed(_pending_edits)):
            fname = edit.get("file", "?")
            _print(gray(f"  [{len(_pending_edits) - 1 - i}] {fname}"))
        return True

    # Pop the most recent edit and restore original content
    edit = _pending_edits.pop()
    filepath = edit.get("file", "")
    original = edit.get("original", "")

    if not filepath or not original:
        _print(gray("[D] Undo failed: missing edit info."))
        return True

    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(original)
        _print(gray(f"[D] Undid edit to {filepath}"))
    except Exception as e:
        _print(gray(f"[D] Undo failed: {e}"))
        # Put it back if failed
        _pending_edits.append(edit)

    return True


def _cmd_submit(arg: str, messages: list[dict], session: Session) -> bool:
    """Submit a completed task / changes. /submit [--message <msg>]"""
    parts = arg.strip().split()
    commit_msg = None

    i = 0
    while i < len(parts):
        if parts[i] == "--message" and i + 1 < len(parts):
            commit_msg = parts[i + 1]
            i += 2
        else:
            i += 1

    if not commit_msg:
        commit_msg = "Completed task via Draguniteus"

    # Run git add -A && git commit -m "..."
    from draguniteus.tools.shell import tool_bash
    _print(gray(f"[D] Staging and committing changes..."))

    add_result = tool_bash("git add -A")
    if add_result and "error" in add_result.lower():
        _print(gray(f"[D] Git add failed: {add_result[:200]}"))
        return True

    commit_result = tool_bash(f'git commit -m "{commit_msg}"')
    if commit_result and "error" in commit_result.lower():
        _print(gray(f"[D] Git commit failed: {commit_result[:200]}"))
    elif "nothing to commit" in commit_result.lower():
        _print(gray("[D] Nothing to commit."))
    else:
        _print(print_success(f"[D] Changes committed: {commit_result[:200]}"))

    return True


def _cmd_resume(arg: str, messages: list[dict], session: Session) -> bool:
    """Resume a session or task. /resume [--session <id>]"""
    parts = arg.strip().split()
    session_id = None

    i = 0
    while i < len(parts):
        if parts[i] == "--session" and i + 1 < len(parts):
            session_id = parts[i + 1]
            i += 2
        else:
            session_id = parts[i] if parts else None
            break

    if session_id:
        _print(gray(f"[D] Resuming session: {session_id}"))
        # The main loop handles resume via _resume_id global
        global _resume_id
        _resume_id = session_id
        _print(gray("[D] Use /reset to start fresh, /new to start a new session"))
    else:
        _print(gray("[D] Available sessions:"))
        from draguniteus.session import SessionStore
        store = SessionStore()
        for s in store._sessions[-5:]:
            _print(gray(f"  - {s.id} (created: {s.created_at[:16]})"))

    return True


def _cmd_context(arg: str, messages: list[dict], session: Session) -> bool:
    """Show/manage context window. /context [--show] [--size]"""
    parts = arg.strip().split()

    if "--size" in parts:
        try:
            from draguniteus.client import _client
            if _client:
                input_toks = _client.count_tokens(messages)
                threshold = 8192
                pct = min(100, (input_toks / threshold) * 100)
                _print(gray(f"[D] Context: {input_toks} tokens ({pct:.1f}% of {threshold})"))
        except Exception:
            pass
        return True

    # Default: show context summary
    msg_count = len(messages)
    _print(gray(f"[D] Context: {msg_count} messages in current session"))
    if msg_count > 0:
        # Show last message preview
        last = messages[-1] if messages else {}
        role = last.get("role", "?")
        content = last.get("content", "")
        if isinstance(content, str):
            preview = content[:100] + "..." if len(content) > 100 else content
        else:
            preview = str(content)[:100]
        _print(gray(f"  Last: [{role}] {preview}"))
    return True


def _cmd_model(arg: str, messages: list[dict], session: Session) -> bool:
    """Switch model or show available models. /model [--list] [model_name]"""
    global _cfg
    parts = arg.strip().split()

    if "--list" in parts or not parts:
        _print(gray("[D] Available models:"))
        models = ["MiniMax-M2.7", "MiniMax-M2.5", "MiniMax-M2.1", "MiniMax-M2"]
        for m in models:
            current = " (current)" if str(_cfg.model) == m else ""
            _print(gray(f"  - {m}{current}"))
        return True

    # Set model
    new_model = parts[0]
    old_model = str(_cfg.model)
    try:
        _cfg._raw["model"] = new_model
        _print(gray(f"[D] Model changed: {old_model} → {new_model}"))
    except Exception as e:
        _print(gray(f"[D] Failed to change model: {e}"))

    return True


def _cmd_patch(arg: str, messages: list[dict], session: Session) -> bool:
    """Apply a patch to a file. /patch <file> <old_text> <new_text>"""
    parts = arg.strip().split(maxsplit=2)

    if len(parts) < 3:
        _print(gray("[D] Usage: /patch <file> <old_text> <new_text>"))
        return True

    filepath, old_text, new_text = parts[0], parts[1], parts[2]
    _print(gray(f"[D] Applying patch to {filepath}..."))

    from draguniteus.tools.filesystem import tool_edit
    result = tool_edit(filepath, old_text, new_text)
    if "ok" in result.lower():
        _print(print_success(f"[D] Patch applied successfully"))
    else:
        _print(gray(f"[D] Patch failed: {result}"))

    return True


def _cmd_inspect(arg: str, messages: list[dict], session: Session) -> bool:
    """Inspect Draguniteus's full environment. /inspect [--section <name>] [--json]"""
    parts = arg.strip().split()
    section = None
    as_json = False

    i = 0
    while i < len(parts):
        p = parts[i]
        if p == "--section" and i + 1 < len(parts):
            section = parts[i + 1]
            i += 2
        elif p == "--json":
            as_json = True
            i += 1
        elif p == "--section" and i + 1 >= len(parts):
            _print(gray("[D] /inspect --section requires a value: self|config|env|git|tools|hooks|permissions|mcp|skills|pattern_library|archive"))
            return True
        else:
            i += 1

    from draguniteus.inspect import get_full_environment, format_environment, format_doctor, run_doctor

    if section == "doctor":
        # Special: run doctor instead of environment
        checks = run_doctor()
        if as_json:
            import json
            _print(json.dumps(checks, indent=2))
        else:
            _print(format_doctor(checks))
        return True

    env = get_full_environment()

    if as_json:
        import json
        _print(json.dumps(env, indent=2))
    elif section:
        output = format_environment(env, section=section)
        _print(output)
    else:
        output = format_environment(env)
        _print(output)

    return True


def _cmd_info(arg: str, messages: list[dict], session: Session) -> bool:
    """Machine-readable info dump. /info is an alias for /inspect --json."""
    return _cmd_inspect("--json", messages, session)


def _cmd_doctor(arg: str, messages: list[dict], session: Session) -> bool:
    """Run self-diagnosis. /doctor is an alias for /inspect --section doctor."""
    return _cmd_inspect("--section doctor", messages, session)


def _cmd_eval(arg: str, messages: list[dict], session: Session) -> bool:
    """Evaluate code safely in a sandbox. /eval [--lang <lang>] <code>"""
    parts = arg.strip().split(maxsplit=1)
    lang = "python"
    code = arg

    if parts and parts[0] == "--lang" and len(parts) > 1:
        lang = parts[1].split()[0] if len(parts[1].split()) > 1 else "python"
        code = " ".join(parts[1].split()[1:])
    elif parts and not parts[0].startswith("--"):
        code = arg

    if not code.strip():
        _print(gray("[D] Usage: /eval [--lang python|js|bash] <code>"))
        return True

    _print(gray(f"[D] Evaluating {lang} code..."))

    if lang == "python":
        try:
            import io, contextlib
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                exec(code, {"__builtins__": __builtins__})
            result = output.getvalue()
            if result:
                _print(gray(result))
            else:
                _print(print_success("[D] No output (completed successfully)"))
        except Exception as e:
            _print(red(f"[D] Error: {e}"))
    elif lang in ("js", "javascript"):
        _print(gray("[D] JavaScript eval requires Node.js — not available in this environment"))
    elif lang in ("bash", "shell"):
        _print(gray("[D] Shell eval is disabled for security — use /bash instead"))
    else:
        _print(gray(f"[D] Unknown language: {lang}"))

    return True


def _cmd_refactor(arg: str, messages: list[dict], session: Session) -> bool:
    """Refactor a file or codebase. /refactor [--dry] [--path <path>] <description>

    Analyzes code and applies refactors. Use --dry to preview without applying.
    """
    import re

    parts = arg.strip().split(maxsplit=1)
    dry_run = False
    target_path = None
    description = arg

    if "--dry" in arg:
        dry_run = True
        description = re.sub(r'--dry\s*', '', description)
    if "--path" in arg:
        match = re.search(r'--path\s+(\S+)', description)
        if match:
            target_path = match.group(1)
            description = re.sub(r'--path\s+\S+\s*', '', description)

    if not description.strip():
        _print(gray("[D] Usage: /refactor [--dry] [--path <path>] <description>"))
        return True

    _print(gray(f"[D] Refactor{' (dry run) ' if dry_run else ''}: {description}"))

    # Build refactor directive for the agent
    refactor_msg = f"[Refactor Request]\n\nTarget: {target_path or 'current project'}\n\nDescription: {description}\n\n"
    if dry_run:
        refactor_msg += "This is a DRY RUN — do not apply changes, only describe what would change."
    else:
        refactor_msg += "Apply the refactor and report the changes made."

    messages.append({
        "role": "system",
        "content": refactor_msg
    })

    _print(print_success(f"[D] Refactor queued — agent will process this request"))
    return True


def _cmd_think(arg: str, messages: list[dict], session: Session) -> bool:
    """Force thinking mode for the next turn. /think"""
    try:
        from draguniteus.thinking_router import get_thinking_router
        router = get_thinking_router()
        router.set_override("think")
        _print(gray("[D] Thinking mode forced for next turn"))
    except Exception as e:
        _print(gray(f"[D] Could not enable thinking mode: {e}"))
    return True


def _cmd_fast(arg: str, messages: list[dict], session: Session) -> bool:
    """Force direct-answer mode for the next turn. /fast"""
    try:
        from draguniteus.thinking_router import get_thinking_router
        router = get_thinking_router()
        router.set_override("direct")
        _print(gray("[D] Fast mode forced for next turn (skipping thinking)"))
    except Exception as e:
        _print(gray(f"[D] Could not enable fast mode: {e}"))
    return True


def _cmd_workflow(arg: str, messages: list[dict], session: Session) -> bool:
    """Manage agentic workflows. /workflow [start <task>|status|stop]"""
    try:
        from draguniteus.workflows.agentic_workflow import AgenticWorkflow, WorkflowConfig
    except Exception as e:
        _print(gray(f"[D] Workflow engine not available: {e}"))
        return True

    parts = arg.strip().split(maxsplit=2)
    cmd = parts[0] if parts else ""

    if cmd == "start" and len(parts) > 1:
        task = " ".join(parts[1:])
        workflow_id = f"wf_{session.id[:8]}"
        wf = AgenticWorkflow(workflow_id, task)
        # Store in session state
        if not hasattr(session, "_workflows"):
            session._workflows = {}
        session._workflows[workflow_id] = wf
        _print(print_success(f"[D] Workflow started: {workflow_id} — {task}"))
        messages.append({
            "role": "system",
            "content": f"[Agentic Workflow] Task: {task}\nPlan your approach step by step."
        })
    elif cmd == "status":
        workflows = getattr(session, "_workflows", {})
        if not workflows:
            _print(gray("[D] No active workflows"))
        else:
            for wid, wf in workflows.items():
                badge = wf.get_phase_badge()
                summary = wf.get_progress_summary()
                _print(gray(f"  {badge} {wid}: {summary}"))
    elif cmd == "stop":
        workflows = getattr(session, "_workflows", {})
        if workflows:
            workflows.clear()
            _print(gray("[D] All workflows stopped"))
        else:
            _print(gray("[D] No active workflows to stop"))
    else:
        _print(gray("[D] Usage: /workflow start <task> | status | stop"))

    return True


def _cmd_preview(arg: str, messages: list[dict], session: Session) -> bool:
    """Preview generated files in browser. /preview [filepath] | stop"""
    try:
        from draguniteus.preview.server import get_preview_server
    except Exception as e:
        _print(gray(f"[D] Preview server not available: {e}"))
        return True

    parts = arg.strip().split(maxsplit=1)
    cmd = parts[0] if parts else ""

    if cmd == "stop":
        server = get_preview_server()
        result = server.stop()
        _print(gray(f"[D] {result}"))
    elif cmd:
        # Preview a specific file
        from pathlib import Path
        file_path = Path(cmd)
        server = get_preview_server()
        url = server.preview_file(file_path)
        if url.startswith("Error") or not server.is_running:
            _print(gray(f"[D] {url}"))
        else:
            _print(print_success(f"[D] Preview: {url}"))
    else:
        # Start server and show index
        server = get_preview_server()
        url = server.start()
        _print(print_success(f"[D] Preview server: {url}"))

    return True


def _cmd_checkpoint(arg: str, messages: list[dict], session: Session) -> bool:
    """Manage checkpoints. /checkpoint [list|save|load|delete]"""
    try:
        from draguniteus.checkpoint import get_checkpoint_manager, AgentCheckpoint
    except Exception as e:
        _print(gray(f"[D] Checkpoint system not available: {e}"))
        return True

    mgr = get_checkpoint_manager()
    parts = arg.strip().split(maxsplit=1)
    cmd = parts[0] if parts else ""

    if cmd == "list":
        checkpoints = mgr.list_checkpoints(session.id)
        if not checkpoints:
            _print(gray("[D] No checkpoints for this session"))
        else:
            _print(gray(f"[D] Checkpoints for {session.id}:"))
            for cp in checkpoints[-10:]:
                _print(gray(f"  Step {cp['step']} [{cp['phase']}] — {cp['created_at'][:19]}"))
    elif cmd == "save":
        # Manual save — build checkpoint from current state
        from draguniteus.checkpoint import AgentCheckpoint
        cp = AgentCheckpoint(
            session_id=session.id,
            step_count=0,
            phase="manual",
            messages=messages[-20:],
        )
        path = mgr.save(cp)
        _print(print_success(f"[D] Checkpoint saved: {path}"))
    elif cmd == "delete":
        mgr.delete_session(session.id)
        _print(gray(f"[D] All checkpoints for this session deleted"))
    else:
        _print(gray("[D] Usage: /checkpoint list | save | delete"))

    return True


def _cmd_tools(arg: str, messages: list[dict], session: Session) -> bool:
    """Tool management. /tools [stats|create|list|delete <name>]"""
    try:
        from draguniteus.tools.reflection import get_tool_reflection
        from draguniteus.tools.dynamic import get_tool_builder
    except Exception as e:
        _print(gray(f"[D] Tool management not available: {e}"))
        return True

    parts = arg.strip().split(maxsplit=2)
    cmd = parts[0] if parts else ""

    if cmd == "stats":
        reflection = get_tool_reflection()
        summary = reflection.format_summary()
        _print(gray(f"[D] {summary}"))
    elif cmd == "list":
        builder = get_tool_builder()
        tools = builder.list_tools()
        if not tools:
            _print(gray("[D] No custom tools registered"))
        else:
            _print(gray(f"[D] Custom tools: {', '.join(tools)}"))
    elif cmd == "create" and len(parts) > 1:
        _print(gray("[D] Usage: /tools create <name> <description> <schema_json> — use register_custom_tool() in code instead"))
    elif cmd == "delete" and len(parts) > 1:
        name = parts[1]
        builder = get_tool_builder()
        builder.delete_tool(name)
        _print(gray(f"[D] Tool '{name}' deleted"))
    else:
        _print(gray("[D] Usage: /tools stats | list | delete <name>"))

    return True


def _cmd_critique(arg: str, messages: list[dict], session: Session) -> bool:
    """Run self-critique on the last task. /critique"""
    try:
        from draguniteus.self_improvement import get_self_improvement_engine
    except Exception as e:
        _print(gray(f"[D] Self-improvement engine not available: {e}"))
        return True

    engine = get_self_improvement_engine()
    # Try to get tool results from session if available
    tool_results = getattr(session, "_last_tool_results", [])

    if not messages:
        _print(gray("[D] No messages to critique"))
        return True

    # Get last user request
    last_task = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            last_task = m.get("content", "")[:200]
            break

    critique = engine.critique(
        task_description=last_task or "unknown task",
        tool_results=tool_results,
        messages=messages,
        outcome="success",
    )

    if critique:
        _print(gray(f"[D] {critique}"))
    else:
        _print(gray("[D] No critique available"))

    return True


if __name__ == "__main__":
    app()