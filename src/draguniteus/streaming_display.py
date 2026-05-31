"""Progressive streaming display — matches Claude Code's real-time output.

Uses Rich.Live for anchored thinking line at bottom of terminal while
response content streams above it. This ensures the thinking line stays
in place and overwrites itself, not scrolling with content.

Features:
  - Rich.Live for fixed-position thinking line (stays at bottom, overwrites in place)
  - Animated star spinner cycle: · ✢ ✳ ✶ ✻ ✽ (Claude Code premium style)
  - Elapsed time display
  - Token count tracking
  - Tool bullets shown above thinking line
  - Intensity indicators ("almost done thinking with max effort")

After streaming completes, the live display stops cleanly and normal
output continues with content above the cleared thinking line area.
"""
from __future__ import annotations

import itertools
import os
import sys
import time
from typing import Any

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
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
    """Set the global live output handler for real-time tool streaming."""
    global _live_output_handler
    _live_output_handler = handler


def live_output_line(line: str, is_stderr: bool = False) -> None:
    """Write a single line of tool output immediately with aggressive flushing."""
    global _live_output_handler
    if _live_output_handler:
        try:
            _live_output_handler(line, is_stderr)
        except Exception:
            pass
    else:
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


class ThinkingLine:
    """A simple class that holds thinking line data, rendered as Rich Text."""

    def __init__(
        self,
        spinner: str,
        verb: str,
        elapsed: str,
        tokens: str = "",
        lines_added: str = "",
        phase: str = "",
        intensity: str = "",
        color: str = "",
        streaming: bool = True,
    ):
        self.spinner = spinner
        self.verb = verb
        self.elapsed = elapsed
        self.tokens = tokens
        self.lines_added = lines_added
        self.phase = phase
        self.intensity = intensity
        self.color = color or DIM
        self.streaming = streaming

    def to_rich_text(self) -> Text:
        """Convert to Rich Text for display."""
        # Format: + Reasoning... (or + Thinking...) - Claude Code style
        # The + prefix indicates live streaming
        prefix = f"{ORANGE}+{RESET} "
        parts = [f"{prefix}{self.color}{self.verb}...{RESET}"]
        parts.append(f"({self.elapsed})")

        if self.tokens:
            parts.append(f"{DIM}{self.tokens}{RESET}")
        if self.lines_added:
            parts.append(f"{DIM}{self.lines_added}{RESET}")
        if self.phase:
            parts.append(f" {self.phase}")
        if self.intensity:
            parts.append(f"{DIM}{self.intensity}{RESET}")

        return Text(" ".join(parts))


class StreamingDisplay:
    """Manages layered progressive display during agent streaming.

    Live streaming UX features (Claude Code style):
    - "+ Reasoning..." status at top with orange + prefix
    - Real-time steering tip: "Send messages while it works to steer in real-time"
    - Bottom shows "esc to interrupt" during streaming
    - After is_final=True the live display stops and content stays.
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
        self._tool_name: str | None = None
        self._tool_path: str = ""
        self._tool_args: str = ""
        # Rich.Live state
        self._live: Live | None = None
        self._thinking_line: ThinkingLine | None = None
        self._response_lines: list[str] = []
        self._tool_bullets: list[str] = []
        self._thinking_active: bool = False
        self._thinking_done: bool = False
        self._tip_shown: bool = False

    def start(self, start_time: float) -> None:
        """Begin the display. Creates Rich.Live for thinking line with Claude Code UX."""
        self._start_time = start_time
        self._thinking = ""
        self._response = ""
        self._token_count = 0
        self._elapsed = 0.0
        self._spinner_cycle = itertools.cycle(STAR_SPINNERS)
        self._spinner_index = 0
        self._thinking_verb = get_thinking_verb()
        self._lines_added = 0
        self._tool_name = None
        self._tool_path = ""
        self._tool_args = ""
        self._response_lines = []
        self._tool_bullets = []
        self._thinking_active = False
        self._thinking_done = False
        self._tip_shown = False

        if self.full_drama:
            # Print real-time steering tip (Claude Code style)
            self._show_streaming_tip()

            # Create initial thinking line
            self._update_thinking_line()

            # Create Rich.Live with the thinking line
            self._live = Live(
                self._thinking_line,
                console=self.console,
                refresh_per_second=10,
                transient=False,  # Keep content after stop
            )
            self._live.start()

    def _show_streaming_tip(self) -> None:
        """Show the real-time steering tip - Claude Code UX feature."""
        if self._tip_shown:
            return
        self._tip_shown = True
        try:
            from draguniteus.theming import DIM, RESET
            tip = f"{DIM}Tip: Send messages while it works to steer in real-time{RESET}\n"
            sys.stdout.buffer.write(tip.encode('utf-8', errors='replace'))
            sys.stdout.buffer.flush()
        except Exception:
            pass

    def _update_thinking_line(self) -> None:
        """Update the thinking line renderable."""
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
        if hasattr(self, '_workflow_phase') and self._workflow_phase:
            phase_badge = f" {self._workflow_phase}"

        # Get current spinner
        spinner = STAR_SPINNERS[self._spinner_index]

        self._thinking_line = ThinkingLine(
            spinner=spinner,
            verb=self._thinking_verb,
            elapsed=elapsed_str,
            tokens=token_str,
            lines_added=lines_str,
            phase=phase_badge,
            intensity=intensity,
        )

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
        """Update display on each streaming event."""
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
        self._spinner_index = (self._spinner_index + 1) % len(STAR_SPINNERS)

        # Change verb when thinking block ends (now generating response)
        if thinking_done and not thinking_active:
            self._thinking_verb = "Generating"
        else:
            self._thinking_verb = get_thinking_verb()

        # Update thinking line via Rich.Live (in-place, anchored at bottom)
        if self.full_drama and self._live:
            # Always regenerate the thinking line
            self._update_thinking_line()

            # Pass the Rich Text renderable to Live.update(), not the raw ThinkingLine object
            if self._thinking_line is not None:
                self._live.update(self._thinking_line.to_rich_text(), refresh=True)

    def show_tool_start(self, tool_name: str, args_display: str = "", path: str = "") -> None:
        """Show a pulsing tool-start bullet immediately when tool_use block starts."""
        if not self.full_drama:
            return

        self._tool_name = tool_name
        self._tool_args = args_display
        self._tool_path = path

        # Store tool bullet for potential use
        bullet = f"  \033[34m●\033[0m \033[36m{tool_name}\033[0m({args_display})\033[90m…\033[0m"
        self._tool_bullets.append(bullet)

        # Immediately print to stdout (above the Live display)
        try:
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
            header = f"\n  {cyan}--- {title} ({total} line{'s' if total != 1 else ''}) ---\n"
            sys.stdout.buffer.write(header.encode('utf-8', errors='replace'))

            for i, line in enumerate(display_lines):
                line = line.rstrip("\r")
                if not line:
                    sys.stdout.buffer.write("  \n".encode('utf-8', errors='replace'))
                    continue

                if any(k in line for k in ["error", "ERROR", "failed", "FAILED", "FAIL"]):
                    color = RED
                elif any(k in line for k in ["warning", "WARNING", "WARN", "deprecated"]):
                    color = YELLOW
                elif any(k in line for k in ["pass", "PASS", "ok", "OK", "success", "SUCCESS"]):
                    color = GREEN
                elif line.startswith("+") or line.startswith(">"):
                    color = CYAN
                elif line.startswith("---") or line.startswith("==="):
                    color = DIM
                elif "│" in line or "└" in line or "┌" in line or "├" in line:
                    color = CYAN
                else:
                    color = WHITE

                sys.stdout.buffer.write(f"  {color}{line}{reset}\n".encode('utf-8', errors='replace'))

                if i > 0 and i % 50 == 0:
                    sys.stdout.buffer.flush()

            if truncated:
                footer = f"  {dim}... ({total - max_lines} more lines) ...{reset}\n"
                sys.stdout.buffer.write(footer.encode('utf-8', errors='replace'))

            footer = f"  {cyan}--- end ---{reset}\n"
            sys.stdout.buffer.write(footer.encode('utf-8', errors='replace'))
            sys.stdout.buffer.flush()

        except Exception:
            pass

    def set_search_context(self, patterns: list[str], files_reading: list[str], current_file: str = "") -> None:
        """Set search context for display."""
        # Could be used for future enhancement
        pass

    def set_lines_added(self, count: int) -> None:
        """Update lines-added counter."""
        self._lines_added = count
        if self.full_drama and self._live:
            self._update_thinking_line()
            self._live.update(self._thinking_line, refresh=True)

    def set_background_tasks(self, enabled: bool) -> None:
        """Update background tasks mode."""
        pass

    def set_workflow_phase(self, phase: str) -> None:
        """Set the workflow phase badge."""
        self._workflow_phase = phase
        if self.full_drama and self._live:
            self._update_thinking_line()
            self._live.update(self._thinking_line, refresh=True)

    def stop(self) -> None:
        """Stop the Live display cleanly."""
        if self._live:
            try:
                self._live.stop()
            except Exception:
                pass
            self._live = None

    def clear_thinking_line(self) -> None:
        """Clear the thinking line (called when switching to response)."""
        # Stop the Live display - content stays, thinking line goes away
        self.stop()

    def show_thinking_content(self, thinking: str) -> None:
        """Show thinking content on its own lines when thinking block ends."""
        # Could show thinking preview here if desired
        pass

    @staticmethod
    def _format_elapsed(seconds: float) -> str:
        if seconds >= 60:
            mins = int(seconds // 60)
            secs = int(seconds % 60)
            return f"{mins}m {secs}s"
        return f"{seconds:.1f}s"