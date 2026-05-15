"""Arena Mode: Model comparison matrix for parallel multi-agent runs.

When 3+ agents with different models run simultaneously, shows a live
comparison matrix with speed, quality, and tool usage per model.

Usage:
    arena = ArenaMode()
    arena.start(agents=[
        {"name": "explorer", "model": "MiniMax-M2.7", "task": "Analyze project"},
        {"name": "security", "model": "MiniMax-M2.5", "task": "Security audit"},
        {"name": "performance", "model": "MiniMax-M2.1", "task": "Performance review"},
    ])
    # Update as agents complete:
    arena.update("explorer", speed=45.2, quality=9, tools_used=5)
    arena.finalize("explorer", final_text="Found 3 issues")
    result = arena.stop()  # Returns comparison summary
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any

try:
    from rich.console import Console
    from rich.table import Table
    from rich.live import Live
    from rich.panel import Panel
    from rich.text import Text
    from rich.grid import Grid
    HAS_RICH = True
except ImportError:
    HAS_RICH = False


@dataclass
class AgentMetrics:
    """Metrics for a single agent in the arena."""
    name: str
    model: str
    speed_s: float | None = None
    quality_score: float | None = None
    tools_used: int = 0
    tokens: int = 0
    done: bool = False
    selected: bool = False
    final_text: str = ""


class ArenaMode:
    """Live arena comparison matrix for multi-model agent runs.

    Displays a side-by-side comparison table of all agents with their
    metrics, updating in real-time as agents report progress.
    """

    def __init__(self):
        if not HAS_RICH:
            raise ImportError("Rich required for ArenaMode")
        self._agents: list[AgentMetrics] = []
        self._cols: int = 0
        self._live: Live | None = None
        self._running = threading.Event()
        self._lock = threading.Lock()

    def start(self, agents: list[dict[str, str]]) -> None:
        """Start the arena display.

        Args:
            agents: List of agent configs with 'name', 'model', 'task'
        """
        self._agents = [
            AgentMetrics(name=a["name"], model=a["model"])
            for a in agents
        ]
        self._cols = min(len(agents), 4)  # Max 4 columns
        self._running.set()
        # Run render loop in a daemon thread so it doesn't block the caller
        t = threading.Thread(target=self._render_loop, daemon=True)
        t.start()

    def update(self, name: str, speed_s: float | None = None,
               quality: float | None = None, tools_used: int | None = None,
               tokens: int | None = None) -> None:
        """Update metrics for an agent."""
        with self._lock:
            for a in self._agents:
                if name in a.name or a.name in name:
                    if speed_s is not None:
                        a.speed_s = speed_s
                    if quality is not None:
                        a.quality_score = quality
                    if tools_used is not None:
                        a.tools_used = tools_used
                    if tokens is not None:
                        a.tokens = tokens
                    break

    def finalize(self, name: str, final_text: str = "", selected: bool = False) -> None:
        """Mark an agent as done."""
        with self._lock:
            for a in self._agents:
                if name in a.name or a.name in name:
                    a.done = True
                    a.final_text = final_text
                    a.selected = selected
                    break

    def stop(self) -> dict[str, Any]:
        """Stop the arena display and return comparison summary."""
        self._running.clear()
        if self._live:
            self._live.stop()
            self._live = None

        with self._lock:
            agent_results = []
            for a in self._agents:
                agent_results.append({
                    "name": a.name,
                    "model": a.model,
                    "speed_s": a.speed_s,
                    "quality_score": a.quality_score,
                    "tools_used": a.tools_used,
                    "tokens": a.tokens,
                    "selected": a.selected,
                    "final_text": a.final_text[:200] if a.final_text else "",
                })

        # Pick winner by quality score (or speed if quality tied)
        winner = None
        best_quality = -1
        best_speed = float('inf')
        for a in self._agents:
            if a.done:
                q = a.quality_score or 0
                if q > best_quality:
                    best_quality = q
                    winner = a.name
                elif q == best_quality and a.speed_s is not None:
                    if a.speed_s < best_speed:
                        best_speed = a.speed_s
                        winner = a.name

        return {
            "agents": agent_results,
            "winner": winner,
            "summary": f"{winner or 'No winner'} won the arena",
        }

    def _render_loop(self) -> None:
        """Background thread that re-renders the arena table."""
        console = Console()
        self._live = Live(console=console, refresh_per_second=4, transient=False)

        def build_table() -> Table:
            table = Table(show_header=True, header_style="bold cyan", box=None)
            table.add_column("Agent", style="bold")
            table.add_column("Model", style="dim")
            table.add_column("Speed", justify="right")
            table.add_column("Quality", justify="right")
            table.add_column("Tools", justify="right")
            table.add_column("Status")

            with self._lock:
                for a in self._agents:
                    speed_str = f"{a.speed_s:.1f}s" if a.speed_s else "—"
                    quality_str = f"{a.quality_score:.0f}/10" if a.quality_score else "—"
                    tools_str = str(a.tools_used) if a.tools_used else "—"

                    if a.done:
                        status = "✓ Done" if not a.selected else "✓ SELECTED"
                        status_style = "bold green" if a.selected else "green"
                    elif a.speed_s is not None:
                        status = "⚡ Running"
                        status_style = "cyan"
                    else:
                        status = "○ Waiting"
                        status_style = "dim"

                    table.add_row(
                        a.name,
                        a.model,
                        speed_str,
                        quality_str,
                        tools_str,
                        f"[{status_style}]{status}[/{status_style}]",
                    )

            return table

        try:
            self._live.start()
            while self._running.is_set():
                try:
                    self._live.update(build_table())
                    time.sleep(0.25)

                    # Check if all done
                    with self._lock:
                        if all(a.done for a in self._agents):
                            break

                except Exception:
                    time.sleep(0.25)

            self._live.update(build_table())  # Final render with all results

        finally:
            self._live.stop()
            self._live = None

    def get_winner(self) -> str | None:
        """Return the name of the winning agent after all agents complete."""
        with self._lock:
            if not all(a.done for a in self._agents):
                return None
            winner = None
            best_quality = -1
            best_speed = float('inf')
            for a in self._agents:
                q = a.quality_score or 0
                if q > best_quality:
                    best_quality = q
                    winner = a.name
                elif q == best_quality and a.speed_s is not None:
                    if a.speed_s < best_speed:
                        best_speed = a.speed_s
                        winner = a.name
            return winner