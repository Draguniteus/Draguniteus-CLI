"""Task list: track pending/in_progress/complete tasks with Ctrl+T toggle."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from draguniteus.config import DEFAULT_CONFIG_DIR


@dataclass
class TaskItem:
    id: str
    description: str
    status: str  # pending, in_progress, complete
    created_at: str
    completed_at: str | None = None


class TaskList:
    """Manages a task list for tracking progress on multi-step work."""

    def __init__(self, session_id: str | None = None):
        self.session_id = session_id or "default"
        self.tasks_dir = DEFAULT_CONFIG_DIR / "tasks"
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        self.list_file = self.tasks_dir / f"tasklist_{self.session_id}.json"
        self._tasks: list[TaskItem] = []
        self._load()

    def _load(self) -> None:
        """Load tasks from disk."""
        if self.list_file.exists():
            try:
                with open(self.list_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._tasks = [TaskItem(**t) for t in data]
            except (json.JSONDecodeError, ValueError):
                self._tasks = []

    def _save(self) -> None:
        """Save tasks to disk."""
        with open(self.list_file, "w", encoding="utf-8") as f:
            json.dump([asdict(t) for t in self._tasks], f, indent=2)

    def add(self, description: str) -> TaskItem:
        """Add a new task."""
        task_id = f"task_{len(self._tasks) + 1}_{int(time.time())}"
        task = TaskItem(
            id=task_id,
            description=description,
            status="pending",
            created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )
        self._tasks.append(task)
        self._save()
        return task

    def complete(self, task_id: str) -> bool:
        """Mark a task as complete."""
        for task in self._tasks:
            if task.id == task_id:
                task.status = "complete"
                task.completed_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                self._save()
                return True
        return False

    def in_progress(self, task_id: str) -> bool:
        """Mark a task as in progress."""
        for task in self._tasks:
            if task.id == task_id:
                task.status = "in_progress"
                self._save()
                return True
        return False

    def remove(self, task_id: str) -> bool:
        """Remove a task."""
        before = len(self._tasks)
        self._tasks = [t for t in self._tasks if t.id != task_id]
        if len(self._tasks) != before:
            self._save()
            return True
        return False

    def list_all(self) -> list[TaskItem]:
        """List all tasks."""
        return self._tasks

    def list_pending(self) -> list[TaskItem]:
        """List pending tasks."""
        return [t for t in self._tasks if t.status == "pending"]

    def list_in_progress(self) -> list[TaskItem]:
        """List in-progress tasks."""
        return [t for t in self._tasks if t.status == "in_progress"]

    def list_complete(self) -> list[TaskItem]:
        """List completed tasks."""
        return [t for t in self._tasks if t.status == "complete"]

    def clear(self) -> None:
        """Clear all tasks."""
        self._tasks = []
        self._save()

    def summary(self) -> str:
        """Get a summary string of task status."""
        total = len(self._tasks)
        if total == 0:
            return "No active tasks"

        complete = len(self.list_complete())
        in_progress = len(self.list_in_progress())
        pending = len(self.list_pending())

        parts = []
        if complete > 0:
            parts.append(f"{complete} complete")
        if in_progress > 0:
            parts.append(f"{in_progress} in progress")
        if pending > 0:
            parts.append(f"{pending} pending")

        return f"Tasks: {', '.join(parts)}"


# Global instance
task_list = TaskList()