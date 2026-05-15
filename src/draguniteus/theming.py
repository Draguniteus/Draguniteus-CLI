"""Theming: clean terminal output matching Claude Code's style."""
from __future__ import annotations

import sys
from typing import Any

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.text import Text

# ------------------------------------------------------------------
# Console
# ------------------------------------------------------------------

console = Console(force_terminal=True, safe_box=True)

# ------------------------------------------------------------------
# Color helpers (return Text objects for Rich)
# ------------------------------------------------------------------

def gold(text: str) -> Text:
    return Text(text, style="yellow")

def gray(text: str) -> Text:
    return Text(text, style="dim")

def teal(text: str) -> Text:
    return Text(text, style="cyan")

def red(text: str) -> Text:
    return Text(text, style="red")

def orange(text: str) -> Text:
    return Text(text, style="yellow")

def claudebrand(text: str) -> Text:
    """Claude Code brand purple (#bd93f9)."""
    return Text(text, style="#bd93f9")

def thinking(text: str) -> Text:
    """Thinking display — italic dim."""
    return Text(text, style="italic dim")

# ------------------------------------------------------------------
# Clean separator
# ------------------------------------------------------------------

SEPARATOR = "─" * 68

# ------------------------------------------------------------------
# Thinking verbs (minimal, no dragon branding)
# ------------------------------------------------------------------

THINKING_VERBS = ["Cooked", "Prepared", "Simmered", "Seared", "Broiled", "Grilled"]

def get_thinking_verb() -> str:
    return THINKING_VERBS[hash(str(__import__("time").time())) % len(THINKING_VERBS)]

# ------------------------------------------------------------------
# Print helpers
# ------------------------------------------------------------------

def _print(text: str | Text) -> None:
    """Print with fallback for non-Unicode consoles."""
    import sys
    from io import StringIO
    # If stdout is not a TTY, use plain print with ANSI stripped
    if not sys.stdout.isatty():
        import re
        plain = re.sub(r'\[/?[^]]+\]', '', str(text))
        plain = re.sub(r'\x1b\[[0-9;]*m', '', plain)
        try:
            print(plain)
        except Exception:
            pass
        return
    # For TTYs, use Rich console normally
    try:
        console.print(text)
    except (UnicodeEncodeError, OSError):
        plain = re.sub(r'\[/?[^]]+\]', '', str(text))
        plain = re.sub(r'\x1b\[[0-9;]*m', '', plain)
        try:
            print(plain)
        except Exception:
            pass

def print_welcome(
    full_drama: bool = True,
    username: str | None = None,
    model: str = "MiniMax-M2.7",
    effort: str = "High Effort",
    path: str | None = None,
) -> None:
    """Print single-line header matching Claude Code's box-drawing style."""
    import os
    if not full_drama:
        return
    try:
        if username is None:
            username = os.environ.get("USERNAME") or os.environ.get("USER") or "User"
        if path is None:
            path = os.getcwd()
        # Use plain print to avoid Rich Unicode issues on Windows
        print(f"[Draguniteus v0.1.0] {model} with {effort.lower()} -- {path}")
        print()
    except Exception:
        print("Draguniteus v0.1.0")

def print_thinking(seconds: float, full_drama: bool = True) -> None:
    """Print thinking indicator: * Cooked for Xs"""
    if full_drama:
        print(f"* {get_thinking_verb()} for {seconds:.1f}s")

def print_divider(full_drama: bool = True) -> None:
    """Print clean separator between turns."""
    _print(SEPARATOR)

def print_prompt(full_drama: bool = True) -> str:
    """Print the interactive prompt and return user input."""
    try:
        from questionary import text
        result = text(
            "❯ ",
            style=None,
        ).ask()
        return result or ""
    except Exception:
        return input("> ").strip()

def print_error(msg: str, full_drama: bool = True) -> None:
    _print(f"[Error] {msg}")

def print_success(msg: str, full_drama: bool = True) -> None:
    _print(f"[OK] {msg}")

def print_status_line(
    model: str,
    cwd: str,
    git_branch: str | None = None,
    context_pct: float = 0.0,
    cost: float = 0.0,
    duration: float = 0.0,
) -> None:
    """Print Claude Code-style status line at bottom of terminal.

    Format: [model]  cwd  @branch  42%  $0.0012  2.3s
    """
    branch = f"  @{git_branch}" if git_branch else ""
    cost_str = f"  ${cost:.4f}" if cost > 0 else ""
    ctx_str = f"  {context_pct:.0f}%"
    parts = [f"[{model}]", cwd, branch, ctx_str, cost_str, f"{duration:.1f}s"]
    status = "  ".join(parts)
    # Print in dim gray, preceded by a blank line for separation
    print()
    try:
        print(f"\033[90m{status}\033[0m")
    except Exception:
        print(status)

def stream_markdown(text: str, live: Live | None = None) -> None:
    """Render markdown to console, optionally inside a Live display."""
    md = Markdown(text)
    if live:
        live.update(md)
    else:
        _print(md)

def make_thinking_display(thinking: str) -> Text:
    """Create a minimal thinking display block."""
    truncated = thinking[:200] + "..." if len(thinking) > 200 else thinking
    return Text(f"[Thinking...] {truncated}")
