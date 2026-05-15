"""Multi-agent TUI panels with Rich.Grid layout and per-agent Live displays.

Organizes concurrent agent outputs into a grid of side-by-side panels,
each with its own streaming text, thinking indicator, and tool count.
"""
from __future__ import annotations

import threading
import queue
import time
from dataclasses import dataclass, field
from typing import Callable, Any

try:
    from rich.console import Console, Group
    from rich.live import Live
    from rich.panel import Panel
    from rich.text import Text
    from rich.table import Table
    from rich.grid import Grid
    from rich.layout import Layout
    HAS_RICH = True
except ImportError:
    HAS_RICH = False


@dataclass
class AgentPanelState:
    """Mutable state for a single agent panel."""
    name: str
    model: str
    text: str = ""
    thinking: str = ""
    tool_count: int = 0
    done: bool = False
    error: str | None = None
    elapsed_s: float = 0.0
    last_update: float = field(default_factory=time.time)


class AgentPanels:
    """Manages N concurrent agent panels with flicker-free Rich.Live updates.

    Usage:
        panels = AgentPanels(3)
        panels.start()

        # From orchestrator callback (called from subagent threads):
        panels.update_text("explorer", "Analyzing file...")
        panels.update_thinking("explorer", "Looking for patterns...")
        panels.update_tool_count("explorer", 2)
        panels.finalize("explorer", "Found 3 issues")

        # In main thread, render:
        panels.render()

        panels.stop()
    """

    def __init__(self, count: int, title: str = "Draguniteus"):
        if not HAS_RICH:
            raise ImportError("Rich is required for AgentPanels")
        self.count = count
        self.title = title
        self._states: list[AgentPanelState] = []
        self._lock = threading.Lock()
        self._live: Live | None = None
        self._running = threading.Event()
        self._cols = min(count, 3)  # Max 3 columns
        self._rows = (count + self._cols - 1) // self._cols

    def start(self) -> None:
        """Initialize all panels and start the Live display in a background thread."""
        self._states = [
            AgentPanelState(name=f"agent-{i}", model="MiniMax-M2.7")
            for i in range(self.count)
        ]
        self._running.set()
        # Run render loop in a daemon thread so it doesn't block the caller
        t = threading.Thread(target=self._render_loop, daemon=True)
        t.start()

    def stop(self) -> None:
        """Stop the Live display."""
        self._running.clear()
        if self._live:
            try:
                self._live.stop()
            except Exception:
                pass
            self._live = None

    def update_text(self, name_or_index: str | int, text: str) -> None:
        """Update the text for a panel (called from subagent thread)."""
        idx = self._resolve_index(name_or_index)
        if idx is None:
            return
        with self._lock:
            self._states[idx].text = text
            self._states[idx].last_update = time.time()

    def update_thinking(self, name_or_index: str | int, thinking: str) -> None:
        """Update the thinking indicator for a panel."""
        idx = self._resolve_index(name_or_index)
        if idx is None:
            return
        with self._lock:
            self._states[idx].thinking = thinking[:200] if thinking else ""
            self._states[idx].last_update = time.time()

    def update_tool_count(self, name_or_index: str | int, count: int) -> None:
        """Update the tool call count for a panel."""
        idx = self._resolve_index(name_or_index)
        if idx is None:
            return
        with self._lock:
            self._states[idx].tool_count = count
            self._states[idx].last_update = time.time()

    def finalize(self, name_or_index: str | int, final_text: str = "", error: str | None = None) -> None:
        """Mark a panel as done with final text."""
        idx = self._resolve_index(name_or_index)
        if idx is None:
            return
        with self._lock:
            if final_text:
                self._states[idx].text = final_text
            self._states[idx].done = True
            self._states[idx].error = error
            self._states[idx].last_update = time.time()

    def _resolve_index(self, name_or_index: str | int) -> int | None:
        """Resolve name or index to panel index."""
        if isinstance(name_or_index, int):
            if 0 <= name_or_index < self.count:
                return name_or_index
            return None
        # Find by name prefix
        name = str(name_or_index)
        for i, s in enumerate(self._states):
            if name in s.name or s.name in name:
                return i
        return None

    def _render_grid(self) -> "Grid":
        """Build the Rich.Grid for all panels."""
        console = Console()

        # Build header row
        header = Table(show_header=False, box=None, pad_edge_cells=0)
        header.add_column(style="bold cyan")
        running = sum(1 for s in self._states if not s.done)
        header.add_row(f"[D] {self.title} — {self.count} agent(s), {running} running")

        # Build panel grid
        grid = Grid(expand=True)
        grid.add_column()  # col spacing

        for row in range(self._rows):
            row_panels: list[Panel] = []
            for col in range(self._cols):
                idx = row * self._cols + col
                if idx >= self.count:
                    break
                with self._lock:
                    state = self._states[idx]
                panel = self._build_agent_panel(state, console)
                row_panels.append(panel)

            if row_panels:
                grid.add_row(*row_panels)

        return grid

    def _build_agent_panel(self, state: AgentPanelState, console: Console) -> "Panel":
        """Build a single agent Panel."""
        lines: list[str] = []

        # Header with name/model
        lines.append(f"[bold]{state.name}[/bold]  [dim]{state.model}[/dim]")

        # Status line
        if state.error:
            lines.append(f"[red]✗ {state.error}[/red]")
        elif state.done:
            lines.append("[green]✓ Done[/green]")
        elif state.thinking:
            lines.append(f"[cyan]◆[/cyan] [dim]{state.thinking}[/dim]")
        else:
            lines.append("[cyan]◆ Running...[/cyan]")

        # Tool count
        if state.tool_count > 0:
            lines.append(f"  [yellow]⚡ {state.tool_count} tool call(s)[/yellow]")

        # Text content (last 300 chars for display)
        display_text = state.text[-300:] if len(state.text) > 300 else state.text
        if display_text:
            # Strip rich markup for plain display
            import re
            clean = re.sub(r'\[/?[^\]]+\]', '', display_text)
            clean = clean.strip()
            if clean:
                lines.append("")
                # Show first few lines of text
                text_lines = clean.split('\n')[:4]
                for tl in text_lines:
                    tl = tl.strip()
                    if tl:
                        lines.append(f"  [dim]{tl}[/dim]")
                if len(clean.split('\n')) > 4:
                    lines.append("  [dim]...[/dim]")

        content = Text("\n".join(lines))
        return Panel(content, title=f"[{state.name}]", border_style="cyan", padding=0)

    def _render_loop(self) -> None:
        """Background thread: re-renders Live display every 0.5s."""
        console = Console()
        self._live = Live(console=console, refresh_per_second=2, transient=False)

        def get_renderable():
            try:
                return self._render_grid()
            except Exception:
                return Text("[render error]")

        # First render (blocking start)
        self._live.start()
        while self._running.is_set():
            try:
                with self._lock:
                    # Copy current states for rendering
                    states_copy = [AgentPanelState(
                        name=s.name, model=s.model,
                        text=s.text, thinking=s.thinking,
                        tool_count=s.tool_count, done=s.done,
                        error=s.error, elapsed_s=s.elapsed_s
                    ) for s in self._states]

                # Build grid with current states
                grid = Grid(expand=True)
                grid.add_column()

                for row in range(self._rows):
                    row_panels: list[Panel] = []
                    for col in range(self._cols):
                        idx = row * self._cols + col
                        if idx >= self.count:
                            break
                        state = states_copy[idx]
                        panel = self._build_agent_panel(state, console)
                        row_panels.append(panel)
                    if row_panels:
                        grid.add_row(*row_panels)

                self._live.update(grid)
                time.sleep(0.5)

                # Check if all done
                if all(s.done for s in states_copy):
                    break

            except Exception:
                time.sleep(0.5)

        self._live.stop()
        self._live = None

    def create_progress_callback(self, name_or_index: str | int) -> Callable[[str, str, int, bool], None]:
        """Return a callback for use with orchestrator.progress_callback.

        Callback signature: (partial_text, thinking, tool_count, done)
        """
        idx = self._resolve_index(name_or_index)
        if idx is None:
            return lambda *a: None

        def callback(partial_text: str = "", thinking: str = "",
                     tool_count: int = 0, done: bool = False):
            if partial_text:
                self.update_text(idx, partial_text)
            if thinking:
                self.update_thinking(idx, thinking)
            if tool_count is not None:
                self.update_tool_count(idx, tool_count)
            if done:
                self.finalize(idx, partial_text)

        return callback


def create_orchestrator_callback(panels: AgentPanels, name: str, idx: int) -> Callable:
    """Factory to create a per-agent progress callback for the orchestrator."""
    return panels.create_progress_callback(idx)