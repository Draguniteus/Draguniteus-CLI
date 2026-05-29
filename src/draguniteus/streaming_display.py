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
            thinking: accumulated thinking text
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
        if self.full_drama:
            self._thinking_print()

    def _thinking_print(self) -> None:
        """Print thinking line via \r (in-place update on Windows)."""
        elapsed_str = self._format_elapsed(self._elapsed)

        # Build intensity message based on thinking state and elapsed time
        intensity = ""
        if self._thinking_active:
            # Still receiving thinking content
            if self._elapsed > 120:  # 2+ minutes
                intensity = " · almost done thinking with max effort"
            elif self._elapsed > 60:  # 1+ minute
                intensity = " · thinking with max effort"
            elif self._elapsed > 15:
                intensity = " · thought for"
        elif self._thinking_done:
            # Thinking block ended - now generating response
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

        # Build search context line if active
        search_context = ""
        if self._search_patterns or self._files_reading:
            pattern_count = len(self._search_patterns) if self._search_patterns else 0
            file_count = len(self._files_reading) if self._files_reading else 0
            search_context = f"Searching for {pattern_count} pattern{'s' if pattern_count != 1 else ''}, reading {file_count} file{'s' if file_count != 1 else ''}… (ctrl+o to expand)"

        # Workflow phase badge
        phase_badge = ""
        if self._workflow_phase:
            phase_badge = f" {self._workflow_phase}"

        # Build the thinking line (spinner + verb + elapsed + tokens + intensity)
        spinner = getattr(self, '_spinner', STAR_SPINNERS[0])
        line = f"{spinner} {self._thinking_verb}... ({elapsed_str}){token_str}{lines_str}{phase_badge}{intensity}"

        try:
            # Calculate total lines to clear (thinking line + search context + file context)
            total_lines = 1
            if search_context:
                total_lines += 1
            if self._tool_path:
                total_lines += 1

            if self._last_thinking_len > 0:
                # Subsequent update: move cursor UP to the thinking line using ANSI
                # Then \r to start of that line, spaces to clear
                move_up = "\x1b[{}A".format(total_lines)
                clear_lines = move_up + "\r" + " " * min(self._last_thinking_len, 200)
                os.write(1, clear_lines.encode('utf-8', errors='replace'))
            else:
                # First time: move to a new line before printing thinking status
                os.write(1, "\n".encode('utf-8', errors='replace'))

            # Write new thinking line (ending with \n to move cursor to next line)
            os.write(1,(line + "\n").encode('utf-8', errors='replace'))

            # Write search context on next line if active
            if search_context:
                search_line = f"\n  {search_context}"
                os.write(1,search_line.encode('utf-8', errors='replace'))

            # Write file context on next line if active
            if self._tool_path:
                file_context = f"\n  ⎿  {self._tool_path}"
                os.write(1,file_context.encode('utf-8', errors='replace'))

            sys.stdout.buffer.flush()
            self._last_thinking_len = len(line) + 1  # +1 for the \n
        except Exception:
            pass

    def _thinking_print_plain(self) -> None:
        """Fallback plain thinking line without ANSI colors."""
        elapsed_str = self._format_elapsed(self._elapsed)
        spinner = getattr(self, '_spinner', STAR_SPINNERS[0])
        thinking_content = self._thinking[:MAX_THINKING_DISPLAY] if self._thinking else ""
        if thinking_content:
            line = f"\r{spinner} {self._thinking_verb}... ({elapsed_str}) {thinking_content}"
        else:
            line = f"\r{spinner} {self._thinking_verb}... ({elapsed_str})"
        try:
            os.write(1,line.encode('utf-8', errors='replace'))
            sys.stdout.buffer.flush()
            self._last_thinking_len = len(line)
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
            os.write(1,display.encode('utf-8', errors='replace'))
            sys.stdout.buffer.flush()
        except Exception:
            pass

    def show_output(self, output: str, title: str = "output", max_lines: int = 200) -> None:
        """Stream command output inline — colorized by type.

        Args:
            output: raw stdout/stderr from a command
            title: label for this output block (e.g., "output", "errors")
            max_lines: cap on lines to display (prevents token bloat)
        """
        if not output or not self.full_drama:
            return

        lines = output.split("\n")
        total = len(lines)
        display_lines = lines[:max_lines]
        truncated = total > max_lines

        try:
            # Header with line count
            dim = DIM
            reset = RESET
            cyan = CYAN
            header = f"\n  {cyan}--- {title} ({total} line{'s' if total != 1 else ''}) ---{reset}\n"
            os.write(1,header.encode('utf-8', errors='replace'))

            # Colorize based on output characteristics
            for i, line in enumerate(display_lines):
                line = line.rstrip("\r")
                if not line:
                    # Empty line — preserve spacing
                    os.write(1,f"  \n".encode('utf-8', errors='replace'))
                    continue

                # Detect line type for coloring
                if any(k in line for k in ["error", "ERROR", "failed", "FAILED", "FAIL"]):
                    color = RED
                elif any(k in line for k in ["warning", "WARNING", "WARN", "deprecated"]):
                    color = YELLOW
                elif any(k in line for k in ["pass", "PASS", "ok", "OK", "success", "SUCCESS"]):
                    color = GREEN
                elif line.startswith("+") or line.startswith(">"):
                    color = CYAN  # diff/addition lines
                elif line.startswith("---") or line.startswith("==="):
                    color = DIM  # separator lines
                elif "│" in line or "└" in line or "┌" in line or "├" in line:
                    color = CYAN  # box-drawing / tree lines
                else:
                    color = WHITE

                try:
                    os.write(1,f"  {color}{line}{reset}\n".encode('utf-8', errors='replace'))
                except Exception:
                    # Fallback for non-colorable content
                    os.write(1,f"  {line}\n".encode('utf-8', errors='replace'))

                # Flush every 50 lines for streaming effect on large outputs
                if i > 0 and i % 50 == 0:
                    sys.stdout.buffer.flush()

            if truncated:
                footer = f"  {DIM}... ({total - max_lines} more lines) ...{reset}\n"
                os.write(1,footer.encode('utf-8', errors='replace'))

            footer = f"  {cyan}--- end ---{reset}\n"
            os.write(1,footer.encode('utf-8', errors='replace'))
            sys.stdout.buffer.flush()

        except Exception:
            # Fallback: print raw output
            try:
                for line in display_lines[:20]:
                    os.write(1,f"{line}\n".encode('utf-8', errors='replace'))
                sys.stdout.buffer.flush()
            except Exception:
                pass

    def set_search_context(self, patterns: list[str], files_reading: list[str], current_file: str = "") -> None:
        """Set search context for display.

        Args:
            patterns: list of search patterns (e.g., ["foo", "bar"])
            files_reading: list of files being read (e.g., ["config.py", "cli.py"])
            current_file: file currently being processed
        """
        self._search_patterns = patterns
        self._files_reading = files_reading
        self._current_file = current_file
        # Also set tool_path for single file context
        if current_file and not self._tool_path:
            self._tool_path = current_file

    def set_lines_added(self, count: int) -> None:
        """Update lines-added counter."""
        self._lines_added = count

    def set_background_tasks(self, enabled: bool) -> None:
        """Update background tasks mode."""
        self._background_tasks = enabled

    def set_workflow_phase(self, phase: str) -> None:
        """Set the workflow phase badge (e.g., PLANNING, EXEC, VERIFY, ITERATE)."""
        self._workflow_phase = phase

    def stop(self) -> None:
        """Stop the display cleanly."""
        # Clear thinking line
        if self._showing_thinking:
            try:
                clear = "\r" + " " * self._last_thinking_len + "\r"
                os.write(1,clear.encode('utf-8', errors='replace'))
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
