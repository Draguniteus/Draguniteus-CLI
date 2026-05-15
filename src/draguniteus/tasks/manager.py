"""Task management system with UUID-based task tracking."""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from draguniteus.config import Config


class TaskStatus:
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class Task:
    """A background task with metadata."""

    def __init__(self, id: str, command: str, cwd: str, status: str = TaskStatus.PENDING):
        self.id = id
        self.command = command
        self.cwd = cwd
        self.status = status
        self.created_at = datetime.utcnow().isoformat()
        self.updated_at = self.created_at
        self.result: str | None = None
        self.output_path: Path | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "command": self.command,
            "cwd": self.cwd,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "result": self.result,
            "output_path": str(self.output_path) if self.output_path else None,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> Task:
        task = Task(
            id=data["id"],
            command=data["command"],
            cwd=data["cwd"],
            status=data.get("status", TaskStatus.PENDING),
        )
        task.created_at = data.get("created_at", task.created_at)
        task.updated_at = data.get("updated_at", task.updated_at)
        task.result = data.get("result")
        op = data.get("output_path")
        task.output_path = Path(op) if op else None
        return task


class TaskManager:
    """Manages background tasks with UUID-based tracking."""

    def __init__(self, config: Config | None = None):
        self.config = config or Config()
        self.tasks_dir = self.config.config_dir / "tasks"
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        self._tasks: dict[str, Task] = {}
        self._load_all()

    def _load_all(self) -> None:
        """Load all tasks from disk."""
        if not self.tasks_dir.exists():
            return
        for task_dir in self.tasks_dir.iterdir():
            if not task_dir.is_dir():
                continue
            task_file = task_dir / "task.json"
            if task_file.exists():
                try:
                    data = json.loads(task_file.read_text(encoding="utf-8"))
                    task = Task.from_dict(data)
                    self._tasks[task.id] = task
                except Exception:
                    pass

    def _save_task(self, task: Task) -> None:
        """Save task to disk."""
        task_dir = self.tasks_dir / task.id
        task_dir.mkdir(exist_ok=True)
        task_file = task_dir / "task.json"
        task_file.write_text(json.dumps(task.to_dict(), indent=2), encoding="utf-8")

    def create_task(self, command: str, cwd: str | None = None) -> Task:
        """Create a new background task."""
        task_id = str(uuid.uuid4())
        task = Task(
            id=task_id,
            command=command,
            cwd=cwd or str(Path.cwd()),
        )
        self._tasks[task_id] = task
        self._save_task(task)
        return task

    def start_task(self, task_id: str) -> Path | None:
        """Mark a task as in_progress and return its output log path."""
        if task_id not in self._tasks:
            return None
        task = self._tasks[task_id]
        task.status = TaskStatus.IN_PROGRESS
        task.updated_at = datetime.utcnow().isoformat()
        self._save_task(task)

        output_dir = self.tasks_dir / task_id
        output_dir.mkdir(exist_ok=True)
        output_path = output_dir / "output.log"
        task.output_path = output_path
        return output_path

    def complete_task(self, task_id: str, result: str) -> None:
        """Mark a task as completed with result."""
        if task_id not in self._tasks:
            return
        task = self._tasks[task_id]
        task.status = TaskStatus.COMPLETED
        task.result = result
        task.updated_at = datetime.utcnow().isoformat()
        self._save_task(task)

    def fail_task(self, task_id: str, error: str) -> None:
        """Mark a task as failed with error."""
        if task_id not in self._tasks:
            return
        task = self._tasks[task_id]
        task.status = TaskStatus.FAILED
        task.result = error
        task.updated_at = datetime.utcnow().isoformat()
        self._save_task(task)

    def get_task(self, task_id: str) -> Task | None:
        """Get a task by ID."""
        return self._tasks.get(task_id)

    def list_tasks(self, status: str | None = None) -> list[Task]:
        """List all tasks, optionally filtered by status."""
        tasks = list(self._tasks.values())
        if status:
            tasks = [t for t in tasks if t.status == status]
        # Sort by created_at descending
        tasks.sort(key=lambda t: t.created_at, reverse=True)
        return tasks

    def delete_task(self, task_id: str) -> None:
        """Delete a task and its files."""
        if task_id in self._tasks:
            del self._tasks[task_id]
        task_dir = self.tasks_dir / task_id
        if task_dir.exists():
            import shutil
            shutil.rmtree(task_dir)


# Global task manager
_task_manager: TaskManager | None = None


def get_task_manager() -> TaskManager:
    global _task_manager
    if _task_manager is None:
        _task_manager = TaskManager()
    return _task_manager