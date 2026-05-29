"""Theming: clean terminal output matching Claude Code's style."""
from __future__ import annotations

import os
import sys
import time
from typing import Any

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.text import Text

# ------------------------------------------------------------------
# Windows ANSI Support
# ------------------------------------------------------------------

def _enable_windows_ansi() -> None:
    """Enable ANSI escape code support on Windows 10+.

    Windows conhost (PowerShell, cmd.exe) requires Virtual Terminal
    Processing to be enabled for ANSI escape codes to work.
    This is done by setting ENABLE_VIRTUAL_TERMINAL_PROCESSING via SetConsoleMode.
    """
    if os.name != "nt":
        return
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        STD_OUTPUT_HANDLE = -11
        ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
        RESET_MODE = 0x0002
        h = kernel32.GetStdHandle(STD_OUTPUT_HANDLE)
        mode = ctypes.c_ulong()
        if kernel32.GetConsoleMode(h, ctypes.byref(mode)):
            # Enable virtual terminal processing
            kernel32.SetConsoleMode(h, mode.value | ENABLE_VIRTUAL_TERMINAL_PROCESSING)
    except Exception:
        pass

# Enable Windows ANSI on module import
_enable_windows_ansi()

# ------------------------------------------------------------------
# Console
# ------------------------------------------------------------------

console = Console(force_terminal=True, safe_box=True)

# ------------------------------------------------------------------
# Claude Code color palette (ANSI escape codes for Windows compatibility)
# ------------------------------------------------------------------

# Claude brand purple (#bd93f9) - used for header, accept edits on
CLAUDE_PURPLE = "\033[38;5;141m"

# Orange/yellow - used for thinking verbs (✻ Mulling...)
ORANGE = "\033[33m"

# Cyan/teal - used for tool names (Bash, Grep, Read, etc.)
CYAN = "\033[36m"

# Dim gray - used for secondary text (esc to interrupt, ctrl+o, etc.)
DIM = "\033[90m"

# White/bright - used for primary text and bullets (regular responses)
WHITE = "\033[97m"
BRIGHT = "\033[1m"

# Red - used for errors and failed operations
RED = "\033[31m"

# Green - used for success and completed operations
GREEN = "\033[32m"

# Blue - used for bash commands and running operations
BLUE = "\033[34m"

# Yellow - used for warnings
YELLOW = "\033[33m"

# Reset
RESET = "\033[0m"

# ------------------------------------------------------------------
# Claude Code bullet and sub-item symbols
# ------------------------------------------------------------------

# Main bullet (●) - color varies by context
BULLET = "●"

# Sub-item bullet (⎿) - used for indented items like file paths
# This is U+250F BOX DRAWINGS LIGHT DOWN AND RIGHT
SUB_ITEM_BULLET = "⎿"

# Running/thinking indicator variations
RUNNING_BULLET = "●"  # Can be made to blink with ANSI

# Color for sub-item text (typically dim gray or cyan)
SUB_ITEM_COLOR = CYAN  # Use cyan for sub-items like file paths

# ------------------------------------------------------------------
# Bullet helpers (Claude Code uses colored bullets based on context)
# ------------------------------------------------------------------

def print_bullet(text: str, color: str = WHITE) -> None:
    """Print a line with a colored bullet prefix.

    Bullet colors in Claude Code:
    - WHITE: Regular responses
    - CYAN: Bash commands, tools
    - RED: Errors
    - GREEN: Success/completed
    - BLUE: Running operations
    """
    try:
        msg = f"  {color}●{RESET} {text}"
        sys.stdout.buffer.write(f"{msg}\n".encode('utf-8', errors='replace'))
        sys.stdout.buffer.flush()
    except Exception:
        pass


def print_bullet_inline(tool_name: str, args_display: str = "", status: str = "", bullet_color: str = CYAN) -> None:
    """Print an inline tool call bullet with Claude Code styling.

    Format: ● ToolName(args) status
    - Bullet color depends on operation type
    - Tool name is cyan
    - Args are white
    - Status is dim gray
    """
    if status:
        status_str = f"{DIM} ({status}){RESET}"
    else:
        status_str = ""

    try:
        msg = f"  {bullet_color}●{RESET} {CYAN}{tool_name}{RESET}({WHITE}{args_display}{RESET}){status_str}"
        sys.stdout.buffer.write(f"{msg}\n".encode('utf-8', errors='replace'))
        sys.stdout.buffer.flush()
    except Exception:
        pass


def print_running_bullet(tool_name: str, args_display: str = "", elapsed: str = "", timeout: str = "") -> None:
    """Print a bullet for a running operation (blue bullet).

    Format: ● ToolName(args) (status)
    """
    if elapsed and timeout:
        status = f"Running… ({elapsed} · timeout {timeout}s)"
    elif elapsed:
        status = f"Running… ({elapsed})"
    else:
        status = "Running…"
    print_bullet_inline(tool_name, args_display, status, BLUE)


def print_error_bullet(text: str) -> None:
    """Print an error bullet (red)."""
    print_bullet(text, RED)


def print_success_bullet(text: str) -> None:
    """Print a success bullet (green)."""
    print_bullet(text, GREEN)


def print_tool_bullet(tool_name: str, args_display: str = "", status: str = "") -> None:
    """Print a tool call bullet (cyan).

    Format: ● ToolName(args) (status)
    """
    print_bullet_inline(tool_name, args_display, status, CYAN)


def print_sub_item(text: str, color: str = SUB_ITEM_COLOR) -> None:
    """Print an indented sub-item using ⎿ symbol (Claude Code style).

    Format:   ⎿  text
    Used for: file paths under tool calls, secondary info, etc.
    """
    try:
        msg = f"  {color}{SUB_ITEM_BULLET}{RESET} {text}"
        sys.stdout.buffer.write(f"{msg}\n".encode('utf-8', errors='replace'))
        sys.stdout.buffer.flush()
    except Exception:
        pass


def print_sub_items(items: list[str], color: str = SUB_ITEM_COLOR) -> None:
    """Print multiple indented sub-items.

    Each item gets its own ⎿ prefix.
    """
    for item in items:
        print_sub_item(item, color)


def print_blinking_bullet(text: str, bullet_color: str = BLUE) -> None:
    """Print a bullet that appears to blink/pulse (for running operations).

    Uses ANSI hide/show cursor or rapid color toggle to simulate blink.
    In pipe mode, falls back to solid color.
    """
    # Try to create blinking effect with cursor hide/show
    # In pipe/non-TTY mode, just show solid
    try:
        # Hide cursor
        sys.stdout.buffer.write(b"\033[?25l")
        msg = f"  {bullet_color}●{RESET} {text}"
        sys.stdout.buffer.write(f"{msg}\n".encode('utf-8', errors='replace'))
        sys.stdout.buffer.flush()
        # Show cursor
        sys.stdout.buffer.write(b"\033[?25h")
    except Exception:
        # Fallback to solid bullet
        print_bullet(text, bullet_color)

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
# Clean separator (full terminal width)
# ------------------------------------------------------------------

def get_separator() -> str:
    """Return a full-width divider matching terminal width."""
    import shutil
    return "─" * shutil.get_terminal_size().columns

SEPARATOR = get_separator()

# ------------------------------------------------------------------
# Thinking verbs (minimal, no dragon branding)
# ------------------------------------------------------------------

THINKING_VERBS = ["Mulling", "Pondering", "Considering", "Examining", "Analyzing", "Processing"]

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
    effort: str = "high effort",
    path: str | None = None,
) -> None:
    """Print branded header matching Claude Code's box-drawing style.

    Layout matches Claude Code:
    - Full-width top divider
    - Header (brand, model, path)
    - Full-width middle divider (frames the prompt area)
    - Prompt line follows in caller
    - Full-width bottom divider (after prompt)
    - ? for shortcuts
    """
    import os
    import sys
    import shutil
    if not full_drama:
        return
    try:
        if username is None:
            username = os.environ.get("USERNAME") or os.environ.get("USER") or "User"
        if path is None:
            path = os.getcwd()

        cols = shutil.get_terminal_size().columns

        # Claude Code header characters: ▐▛███▜▌ (U+2590, U+259B, U+2588, etc.)
        header_line1 = " ▐▛███▜▌   Draguniteus v0.1.0"
        header_line2 = "▝▜█████▛▘  " + model + " with " + effort + " · API Usage Billing"
        cwd_line = "  ▘▘ ▝▝    " + path

        # Print using buffer to avoid cp1252 encoding issues on Windows
        def write_out(s):
            try:
                sys.stdout.write(s)
                sys.stdout.flush()
            except UnicodeEncodeError:
                sys.stdout.buffer.write(s.encode('utf-8', errors='replace'))
                sys.stdout.buffer.flush()

        # Full-width top divider
        write_out("─" * cols + "\n")
        # Header
        write_out(f"{CLAUDE_PURPLE}{BRIGHT}{header_line1}{RESET}\n")
        write_out(f"{CLAUDE_PURPLE}{BRIGHT}{header_line2}{RESET}\n")
        write_out(f"{DIM}{cwd_line}{RESET}\n")
        # Full-width middle divider (frames prompt area)
        write_out("─" * cols + "\n")
    except Exception as e:
        print("Draguniteus v0.1.0")

# Past-tense verb mapping for completion indicator (Claude Code style)
_PAST_TENSE_VERBS = ["Crunched", "Sautéed", "Examined", "Processed", "Analyzed", "Pondered"]

def _get_past_tense_verb() -> str:
    """Get a past-tense verb for completion indicator, consistent with elapsed time."""
    idx = int(time.time() * 1000) % len(_PAST_TENSE_VERBS)
    return _PAST_TENSE_VERBS[idx]

def _format_duration(seconds: float) -> str:
    """Format seconds as Xm Ys or Y.Ys."""
    if seconds >= 60:
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{mins}m {secs}s"
    return f"{seconds:.1f}s"

def print_thinking(seconds: float, full_drama: bool = True) -> None:
    """Print thinking completion indicator: ✻ [past-verb] for Xs (Claude Code style - orange)."""
    if full_drama:
        verb = _get_past_tense_verb()
        dur = _format_duration(seconds)
        msg = f"✻ {verb} for {dur}"
        try:
            # Orange for thinking verb
            sys.stdout.buffer.write(f"{ORANGE}{msg}{RESET}\n".encode('utf-8', errors='replace'))
            sys.stdout.buffer.flush()
        except Exception:
            pass

def print_divider(full_drama: bool = True) -> None:
    """Print clean separator between turns (full terminal width)."""
    _print(get_separator())

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
        # questionary can fail on Windows conhost/Git Bash (NoConsoleScreenBufferError)
        # Fall back to Python's input() which works reliably everywhere
        return input("❯ ").strip()


def print_permission_prompt(tool: str, detail: str, full_drama: bool = True) -> str:
    """Print inline permission prompt and return user response.

    Claude Code style: shows the command in yellow with warning color,
    prompts with 'Allow / Deny / Allow always' options.
    Works on Windows conhost/pipes where questionary can't prompt.

    Returns 'y' (allow), 'n' (deny), or 'a' (allow always for this project).
    """
    warning = f"\n  \033[33m⚠️  Permission required: {tool}\033[0m"
    detail_display = f"  \033[90m  {detail[:80]}\033[0m"
    prompt = f"\n  \033[90m(y) Allow  (n) Deny  (a) Allow always for this project\033[0m\n❯ "
    try:
        sys.stdout.buffer.write((warning + "\n").encode('utf-8', errors='replace'))
        sys.stdout.buffer.write((detail_display + "\n").encode('utf-8', errors='replace'))
        sys.stdout.buffer.write(prompt.encode('utf-8', errors='replace'))
        sys.stdout.buffer.flush()
    except Exception:
        pass
    try:
        sys.stdout.buffer.flush()
        sys.stdin.flush()
        response = input("").strip().lower()
        if not response:
            response = "y"
        if response in ("a", "allow always"):
            return "a"
        elif response in ("n", "deny", "no"):
            return "n"
        return "y"
    except (EOFError, KeyboardInterrupt):
        return "n"


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
        sys.stdout.buffer.write(f"{DIM}{status}{RESET}\n".encode('utf-8', errors='replace'))
        sys.stdout.buffer.flush()
    except Exception:
        try:
            print(status)
        except Exception:
            pass

def print_recap(text: str) -> None:
    """Print Claude Code-style recap: ※ recap: [text] (dim gray)"""
    lines = text.split('\n')
    first = True
    for line in lines:
        if first:
            recap_line = f"※ recap: {line}"
            first = False
        else:
            recap_line = f"  {line}" if line else ""
        if recap_line:
            try:
                sys.stdout.buffer.write(f"{DIM}{recap_line}{RESET}\n".encode('utf-8', errors='replace'))
                sys.stdout.buffer.flush()
            except Exception:
                pass


def print_bottom_bar(has_edits: bool = False, edit_count: int = 0) -> None:
    """Print Claude Code-style bottom bar with accept edits controls.

    Format: ⏵⏵ accept edits on (shift+tab to cycle) · esc to interrupt
    - "accept edits on" is light purple (Claude brand)
    - "shift+tab to cycle" and "esc to interrupt" are dim gray
    Or when no pending edits: (ctrl+e to expand results) - all dim gray
    """
    if has_edits and edit_count > 0:
        # Purple for "accept edits on", dim for rest
        bar = f"  {CLAUDE_PURPLE}⏵⏵ accept edits on{RESET}{DIM} (shift+tab to cycle) · esc to interrupt{RESET}"
    else:
        bar = f"{DIM}  (ctrl+e to expand results · esc to interrupt){RESET}"
    try:
        sys.stdout.buffer.write(f"{bar}\n".encode('utf-8', errors='replace'))
        sys.stdout.buffer.flush()
    except Exception:
        try:
            print(bar)
        except Exception:
            pass


def print_shortcuts_line() -> None:
    """Print '? for shortcuts' line (Claude Code style, dim gray)."""
    try:
        sys.stdout.buffer.write(f"{DIM}  ? for shortcuts{RESET}\n".encode('utf-8', errors='replace'))
        sys.stdout.buffer.flush()
    except Exception:
        try:
            print(f"{DIM}  ? for shortcuts{RESET}")
        except Exception:
            pass


def print_tool_call(tool_name: str, args_display: str = "", status: str = "") -> None:
    """Print a tool call like Claude Code: ● Bash(command) (status)

    - "●" is white/bright
    - tool_name (Bash, Grep, etc.) is cyan
    - args_display is white
    - status in parentheses is dim gray
    """
    if status:
        status_str = f"{DIM} ({status}){RESET}"
    else:
        status_str = ""

    try:
        msg = f"  {WHITE}●{RESET} {CYAN}{tool_name}{RESET}({WHITE}{args_display}{RESET}){status_str}"
        sys.stdout.buffer.write(f"{msg}\n".encode('utf-8', errors='replace'))
        sys.stdout.buffer.flush()
    except Exception:
        pass


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
