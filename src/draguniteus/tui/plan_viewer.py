"""Plan Viewer: collapsible side panel showing current task plan.

Usage:
    viewer = PlanViewer()
    viewer.open(current_plan)  # plan = AutonomousRefactorer.plan("...")
    viewer.update_step("src/foo.py", "done")  # mark step complete
    viewer.close()  # hide panel

    # Toggle with /plan command in cli.py
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text
    from rich.table import Table
    HAS_RICH = True
except ImportError:
    HAS_RICH = False


@dataclass
class PlanStep:
    """A single step in a refactoring plan."""
    id: str
    file: str
    description: str
    status: str = "pending"  # pending, in_progress, done, failed, skipped
    expanded: bool = False


class PlanViewer:
    """Collapsible panel showing current refactoring plan progress.

    Shows a list of steps with status indicators and expand/collapse
    for detailed step information.
    """

    def __init__(self):
        if not HAS_RICH:
            raise ImportError("Rich required for PlanViewer")
        self._steps: list[PlanStep] = []
        self._open: bool = False
        self._console: Console | None = None
        self._selected_idx: int = 0

    def open(self, plan_or_steps) -> None:
        """Open the plan viewer with a plan object or list of steps.

        Args:
            plan_or_steps: RefactorPlan object OR list of PlanStep dicts
        """
        self._steps = []
        self._open = True

        # Accept either a RefactorPlan object or a list of step dicts
        if hasattr(plan_or_steps, "changes"):
            # It's a RefactorPlan
            plan = plan_or_steps
            for i, change in enumerate(plan.changes):
                self._steps.append(PlanStep(
                    id=f"step-{i}",
                    file=change.get("file", ""),
                    description=change.get("reason", ""),
                    status="done" if change.get("file") in (plan.executed or []) else "pending",
                ))
        elif isinstance(plan_or_steps, list):
            # It's a list of step dicts
            for i, step in enumerate(plan_or_steps):
                self._steps.append(PlanStep(
                    id=step.get("id", f"step-{i}"),
                    file=step.get("file", ""),
                    description=step.get("description", ""),
                    status=step.get("status", "pending"),
                ))

    def update_step(self, file_or_id: str, status: str) -> None:
        """Update the status of a step by file path or step id.

        Args:
            file_or_id: The file path or step id to update
            status: One of pending, in_progress, done, failed, skipped
        """
        for step in self._steps:
            if file_or_id in step.file or file_or_id == step.id:
                step.status = status
                break

    def toggle_expand(self, idx: int | None = None) -> None:
        """Toggle expand/collapse for a step.

        Args:
            idx: Step index to toggle. If None, toggle selected step.
        """
        target = idx if idx is not None else self._selected_idx
        if 0 <= target < len(self._steps):
            self._steps[target].expanded = not self._steps[target].expanded

    def close(self) -> None:
        """Hide the plan viewer."""
        self._open = False

    def is_open(self) -> bool:
        return self._open

    def navigate(self, direction: str) -> None:
        """Navigate up/down through steps.

        Args:
            direction: 'up', 'down', 'top', 'bottom'
        """
        if direction == 'up':
            self._selected_idx = max(0, self._selected_idx - 1)
        elif direction == 'down':
            self._selected_idx = min(len(self._steps) - 1, self._selected_idx + 1)
        elif direction == 'top':
            self._selected_idx = 0
        elif direction == 'bottom':
            self._selected_idx = len(self._steps) - 1

    def render(self, console: "Console | None" = None) -> str:
        """Render the plan viewer as a string.

        Returns empty string if not open.
        """
        if not self._open or not self._steps:
            return ""

        c = console or Console()
        lines: list[str] = []

        lines.append("[bold cyan]📋 Plan Viewer[/bold cyan]")
        lines.append("")

        for i, step in enumerate(self._steps):
            status_icon: str
            status_style: str
            if step.status == "done":
                status_icon = "✅"
                status_style = "green"
            elif step.status == "in_progress":
                status_icon = "⏳"
                status_style = "yellow"
            elif step.status == "failed":
                status_icon = "❌"
                status_style = "red"
            elif step.status == "skipped":
                status_icon = "⏭"
                status_style = "dim"
            else:
                status_icon = "○"
                status_style = "dim"

            marker = "▶" if i == self._selected_idx else " "
            lines.append(f"  {marker} {status_icon} [bold]{step.file}[/bold]")
            lines.append(f"      {step.description[:60]}")

            if step.expanded:
                lines.append(f"       [dim]id: {step.id} | status: {step.status}[/dim]")

        return "\n".join(lines)

    def render_rich(self, console: "Console | None" = None) -> "Panel":
        """Render as a Rich Panel widget.

        Returns None if not open.
        """
        if not self._open or not self._steps:
            return None

        c = console or Console()
        lines: list[Text] = []

        for i, step in enumerate(self._steps):
            status_icon: str
            status_style: str
            if step.status == "done":
                status_icon = "✅"
                status_style = "green"
            elif step.status == "in_progress":
                status_icon = "⏳"
                status_style = "yellow"
            elif step.status == "failed":
                status_icon = "❌"
                status_style = "red"
            elif step.status == "skipped":
                status_icon = "⏭"
                status_style = "dim"
            else:
                status_icon = "○"
                status_style = "dim"

            marker = "▶" if i == self._selected_idx else " "
            file_text = Text(f"  {marker} {status_icon} ", style=status_style)
            file_text.append(step.file, style="bold")
            lines.append(file_text)

            desc_text = Text(f"      {step.description[:60]}", style="dim")
            lines.append(desc_text)

            if step.expanded:
                id_text = Text(f"       id: {step.id} | status: {step.status}", style="dim")
                lines.append(id_text)

        from rich.text import Text as T
        content = T("\n".join(str(t) for t in lines))
        return Panel(content, title="📋 Plan", border_style="cyan", padding=0)


def render_plan_summary(plan) -> str:
    """One-call function to render a RefactorPlan as a summary string.

    Works with any object that has changes/executed/risk attributes.
    """
    if not plan:
        return ""

    total = len(getattr(plan, "changes", []))
    done = len(getattr(plan, "executed", []))
    risk = getattr(plan, "risk", "?")

    return f"Plan: {done}/{total} steps done | Risk: {risk} | Files: {len(getattr(plan, 'files_affected', []))}"