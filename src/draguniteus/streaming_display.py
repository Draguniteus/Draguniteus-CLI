"""Progressive streaming display — matches Claude Code's real-time output.

Uses ANSI carriage-return (\r) for in-place thinking line updates, which works
reliably on Windows conhost unlike cursor-positioning approaches.

Features:
  - Animated star spinner cycle: · ✢ ✳ ✶ ✻ ✽ (Claude Code premium style)
  - Elapsed time display
  - Token count tracking
  - File context visibility (ctrl+o to expand)
  - Thinking content preview
  - Intensity indicators ("almost done thinking with max effort")

After streaming completes, the live display stops cleanly.
"""
from __future__ import annotations

import itertools
import os
import sys
import time
from typing import Any

from rich.console import Console
from rich.markdown import Markdown
from rich.text import Text

from draguniteus.theming import (
    CYAN, DIM, ORANGE, RESET, WHITE, BLUE, RED, GREEN, YELLOW,
    get_thinking_verb, THINKING_VERBS,
)


# Claude Code premium star/flower spinner cycle
STAR_SPINNERS = ['·', '✢', '✳', '✶', '✻', '✽']

MAX_THINKING_DISPLAY = 100  # max thinking content chars to show

# Global live output handler for real-time tool output streaming
# Set by cli.py to enable line-by-line streaming during tool execution
_live_output_handler: callable | None = None


def set_live_output_handler(handler: callable | None) -> None:
    """Set the global live output handler for real-time tool streaming.

    The handler should be a callable that takes (line: str, is_stderr: bool).
    This enables tools like Bash to stream output line-by-line as it's produced.
    """
    global _live_output_handler
    _live_output_handler = handler


def live_output_line(line: str, is_stderr: bool = False) -> None:
    """Write a single line of tool output immediately with aggressive flushing.

    This is called by tools during execution to stream output in real-time.
    Uses sys.stdout.buffer.write for UTF-8 encoding support on Windows.
    """
    global _live_output_handler
    if _live_output_handler:
        try:
            _live_output_handler(line, is_stderr)
        except Exception:
            pass
    else:
        # Default: write directly to stdout via Python's buffered IO (respects UTF-8)
        try:
            dim = "\033[90m"
            reset = "\033[0m"
            if is_stderr:
                line_out = f"  {dim}{line}{reset}\n"
            else:
                line_out = f"  {line}\n"
            sys.stdout.buffer.write(line_out.encode('utf-8', errors='replace'))
            sys.stdout.buffer.flush()
        except Exception:
            pass


class StreamingDisplay:
    """Manages layered progressive display during agent streaming.

    Architecture:
    - Thinking line uses \r carriage-return for in-place ANSI update (works on Windows)
    - Response text flushed directly via sys.stdout.buffer (progressive char streaming)
    - Tool bullets shown inline when tools execute

    After is_final=True the display stops and final content remains.
    """

    def __init__(self, console: Console, full_drama: bool = True):
        self.console = console
        self.full_drama = full_drama
        self._thinking: str = ""
        self._response: str = ""
        self._token_count: int = 0
        self._start_time: float = 0.0
        self._elapsed: float = 0.0
        self._spinner_cycle = itertools.cycle(STAR_SPINNERS)
        self._spinner_index: int = 0
        self._thinking_verb: str = "Thinking"
        self._lines_added: int = 0
        self._showing_thinking: bool = False
        self._last_thinking_len: int = 0
        self._background_tasks: bool = False
        self._tool_name: str | None = None
        self._tool_path: str = ""
        self._tool_args: str = ""
        self._header_printed: bool = False
        # Search context tracking
        self._search_patterns: list[str] = []
        self._files_reading: list[str] = []
        self._current_file: str = ""
        # Workflow phase tracking
        self._workflow_phase: str = ""  # PLANNING/EXEC/VERIFY/ITERATE badge

    def start(self, start_time: float) -> None:
        """Begin the display. Called before the first streaming event."""
        self._start_time = start_time
        self._thinking = ""
        self._response = ""
        self._token_count = 0
        self._elapsed = 0.0
        self._spinner_cycle = itertools.cycle(STAR_SPINNERS)
        self._spinner_index = 0
        self._thinking_verb = get_thinking_verb()
        self._lines_added = 0
        self._showing_thinking = False
        self._last_thinking_len = 0
        self._background_tasks = False
        self._tool_name = None
        self._tool_path = ""
        self._tool_args = ""
        self._header_printed = False
        self._thinking_content_shown = False

    def update(
        self,
        thinking: str,
        response: str,
        tokens: int = 0,
        tool_name: str | None = None,
        tool_args: str = "",
        tool_path: str = "",
        thinking_active: bool = False,
        thinking_done: bool = False,
    ) -> None:
        """Update thinking line on each streaming event.

        Args:
            thinking: accumulated thinking text (ignored - only status shown during streaming)
            response: accumulated response text
            tokens: current output token count
            tool_name: name of tool being called (if any)
            tool_args: args display string for the tool
            tool_path: file path for sub-item display
            thinking_active: True while thinking content is being received
            thinking_done: True once the thinking content block has ended
        """
        self._elapsed = time.time() - self._start_time
        self._thinking = thinking
        self._response = response
        self._token_count = tokens
        self._tool_name = tool_name
        self._tool_args = tool_args
        self._tool_path = tool_path
        self._thinking_active = thinking_active
        self._thinking_done = thinking_done

        # Advance spinner
        if self.full_drama:
            self._spinner_index = (self._spinner_index + 1) % len(STAR_SPINNERS)
            self._spinner = STAR_SPINNERS[self._spinner_index]
            # Change verb when thinking block ends (now generating response)
            if self._thinking_done and not self._thinking_active:
                self._thinking_verb = "Generating"
            else:
                self._thinking_verb = get_thinking_verb()

        # Update thinking line via \r (in-place, works on Windows)
        # NOTE: We do NOT print thinking content here - only the status line
        if self.full_drama:
            self._thinking_print()

    def _thinking_print(self) -> None:
        """Print thinking line that overwrites itself in-place.

        On Windows conhost where ANSI escape codes may not work,
        falls back to just printing the line (may scroll but works).

        On proper terminals (Windows Terminal, Unix), uses \x1b[2K\r
        (erase line + carriage return) for clean in-place overwrite.
        """
        elapsed_str = self._format_elapsed(self._elapsed)

        # Build intensity message based on thinking state and elapsed time
        intensity = ""
        if self._thinking_active:
            if self._elapsed > 120:
                intensity = " · almost done thinking with max effort"
            elif self._elapsed > 60:
                intensity = " · thinking with max effort"
        elif self._thinking_done:
            if self._elapsed > 15:
                intensity = " · almost done with max effort"

        # Token count display
        token_str = ""
        if self._token_count > 0:
            tokens_k = self._token_count / 1000
            token_str = f" · ↓ {tokens_k:.1f}k tokens"

        # Lines added display
        lines_str = ""
        if self._lines_added > 0:
            lines_str = f" · +{self._lines_added} lines"

        # Workflow phase badge
        phase_badge = ""
        if self._workflow_phase:
            phase_badge = f" {self._workflow_phase}"

        # Build the thinking line: spinner + verb + elapsed + tokens + intensity
        spinner = getattr(self, '_spinner', STAR_SPINNERS[0])
        line = f"{spinner} {self._thinking_verb}... ({elapsed_str}){token_str}{lines_str}{phase_badge}{intensity}"

        # CRITICAL: Print thinking line immediately on first call (even before first event)
        # Otherwise nothing appears until streaming events arrive
        try:
            # Check if we should use ANSI escape codes or fallback
            # On Windows conhost, ANSI codes may not work, so we use a simpler approach
            if os.name == 'nt':
                # On Windows, try ANSI first, fall back to simple print
                try:
                    # Try the ANSI approach (works on Windows Terminal, Git Bash, etc.)
                    erase_and_home = "\x1b[2K\r"
                    sys.stdout.buffer.write(erase_and_home.encode('utf-8'))
                    sys.stdout.buffer.write(line.encode('utf-8', errors='replace'))
                    sys.stdout.buffer.flush()
                    sys.stdout.flush()  # Force flush all buffers
                except Exception:
                    # Fallback: print with \r to move to column 0, then flush
                    print(f"\r{line}", end="", flush=True)
            else:
                # Unix/Linux/macOS - use ANSI escape codes
                erase_and_home = "\x1b[2K\r"
                sys.stdout.buffer.write(erase_and_home.encode('utf-8'))
                sys.stdout.buffer.write(line.encode('utf-8', errors='replace'))
                sys.stdout.buffer.flush()
                sys.stdout.flush()  # Force flush all buffers

            self._last_thinking_len = len(line)
            self._showing_thinking = True
        except Exception:
            pass

    def show_thinking_content(self, thinking: str) -> None:
        """Show thinking content on its own lines when thinking block ends.

        Called when thinking_done=True to display the accumulated thinking
        content in a clean, non-intrusive way before response starts.
        """
        if not thinking or not self.full_drama:
            return
        try:
            dim = DIM
            reset = RESET
            # Show first 3 lines of thinking content (or first 300 chars)
            preview = thinking[:300]
            if len(thinking) > 300:
                preview = preview.rsplit('\n', 1)[0] + "\n  [...]"
            else:
                # Take first few lines
                lines = preview.split('\n')
                if len(lines) > 3:
                    preview = "\n".join(lines[:3]) + "\n  [...]"

            # Print thinking content with dim styling (with leading newline to separate from thinking line)
            thinking_display = f"\n  {dim}{preview}{reset}\n"
            sys.stdout.buffer.write(thinking_display.encode('utf-8', errors='replace'))
            sys.stdout.buffer.flush()
        except Exception:
            pass

    def show_tool_start(self, tool_name: str, args_display: str = "", path: str = "") -> None:
        """Show a pulsing tool-start bullet immediately when tool_use block starts."""
        if not self.full_drama:
            return
        self._tool_name = tool_name
        self._tool_args = args_display
        self._tool_path = path
        try:
            bullet = f"\n  \033[34m●\033[0m \033[36m{tool_name}\033[0m({args_display})\033[90m…\033[0m"
            path_display = f"\n    \033[36m⎿\033[0m  {path}\033[90m\033[0m" if path else ""
            display = bullet + path_display
            sys.stdout.buffer.write(display.encode('utf-8', errors='replace'))
            sys.stdout.buffer.flush()
        except Exception:
            pass

    def show_output(self, output: str, title: str = "output", max_lines: int = 200) -> None:
        """Stream command output inline — colorized by type."""
        if not output or not self.full_drama:
            return

        lines = output.split("\n")
        total = len(lines)
        display_lines = lines[:max_lines]
        truncated = total > max_lines

        try:
            dim = DIM
            reset = RESET
            cyan = CYAN
            header = f"\n  {cyan}--- {title} ({total} line{'s' if total != 1 else ''}) ---{reset}\n"
            sys.stdout.buffer.write(header.encode('utf-8', errors='replace'))

            for i, line in enumerate(display_lines):
                line = line.rstrip("\r")
                if not line:
                    sys.stdout.buffer.write("  \n".encode('utf-8', errors='replace'))
                    continue

                if any(k in line for line in ["error", "ERROR", "failed", "FAILED", "FAIL"]):
                    color = RED
                elif any(k in line for line in ["warning", "WARNING", "WARN", "deprecated"]):
                    color = YELLOW
                elif any(k in line for line in ["pass", "PASS", "ok", "OK", "success", "SUCCESS"]):
                    color = GREEN
                elif line.startswith("+") or line.startswith(">"):
                    color = CYAN
                elif line.startswith("---") or line.startswith("==="):
                    color = DIM
                elif "│" in line or "└" in line or "┌" in line or "├" in line:
                    color = CYAN
                else:
                    color = WHITE

                try:
                    sys.stdout.buffer.write(f"  {color}{line}{reset}\n".encode('utf-8', errors='replace'))
                except Exception:
                    sys.stdout.buffer.write(f"  {line}\n".encode('utf-8', errors='replace'))

                if i > 0 and i % 50 == 0:
                    sys.stdout.buffer.flush()

            if truncated:
                footer = f"  {dim}... ({total - max_lines} more lines) ...{reset}\n"
                sys.stdout.buffer.write(footer.encode('utf-8', errors='replace'))

            footer = f"  {cyan}--- end ---{reset}\n"
            sys.stdout.buffer.write(footer.encode('utf-8', errors='replace'))
            sys.stdout.buffer.flush()

        except Exception:
            try:
                for line in display_lines[:20]:
                    sys.stdout.buffer.write(f"{line}\n".encode('utf-8', errors='replace'))
                sys.stdout.buffer.flush()
            except Exception:
                pass

    def set_search_context(self, patterns: list[str], files_reading: list[str], current_file: str = "") -> None:
        """Set search context for display."""
        self._search_patterns = patterns
        self._files_reading = files_reading
        self._current_file = current_file
        if current_file and not self._tool_path:
            self._tool_path = current_file

    def set_lines_added(self, count: int) -> None:
        """Update lines-added counter."""
        self._lines_added = count

    def set_background_tasks(self, enabled: bool) -> None:
        """Update background tasks mode."""
        self._background_tasks = enabled

    def set_workflow_phase(self, phase: str) -> None:
        """Set the workflow phase badge."""
        self._workflow_phase = phase

    def stop(self) -> None:
        """Stop the display cleanly."""
        if self._showing_thinking:
            try:
                clear = "\x1b[2K\r" + " " * self._last_thinking_len + "\x1b[2K\r"
                sys.stdout.buffer.write(clear.encode('utf-8', errors='replace'))
                sys.stdout.buffer.flush()
            except Exception:
                pass
        self._showing_thinking = False

    @staticmethod
    def _format_elapsed(seconds: float) -> str:
        if seconds >= 60:
            mins = int(seconds // 60)
            secs = int(seconds % 60)
            return f"{mins}m {secs}s"
        return f"{seconds:.1f}s"
