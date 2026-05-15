"""Background task management: track async bash commands with Ctrl+B."""
from __future__ import annotations

import json
import subprocess
import threading
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from draguniteus.config import DEFAULT_CONFIG_DIR


@dataclass
class BackgroundTask:
    id: str
    command: str
    started_at: str
    status: str  # running, completed, failed, cancelled
    output_path: str
    exit_code: int | None = None


class BackgroundTaskManager:
    """Manages background tasks with output written to log files."""

    def __init__(self):
        self.tasks_dir = DEFAULT_CONFIG_DIR / "tasks"
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        self.tasks_file = self.tasks_dir / "tasks.json"
        self._tasks: list[BackgroundTask] = []
        self._running_procs: dict[str, subprocess.Popen] = {}
        self._load()

    def _load(self) -> None:
        """Load tasks from disk."""
        if self.tasks_file.exists():
            try:
                with open(self.tasks_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._tasks = [BackgroundTask(**t) for t in data]
            except (json.JSONDecodeError, ValueError):
                self._tasks = []

    def _save(self) -> None:
        """Save tasks to disk."""
        with open(self.tasks_file, "w", encoding="utf-8") as f:
            json.dump([asdict(t) for t in self._tasks], f, indent=2)

    def start(self, command: str, task_id: str | None = None) -> BackgroundTask:
        """Start a background task."""
        if task_id is None:
            task_id = f"btask_{len(self._tasks) + 1}_{int(time.time())}"

        output_path = str(self.tasks_dir / f"{task_id}.log")

        task = BackgroundTask(
            id=task_id,
            command=command,
            started_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            status="running",
            output_path=output_path,
        )
        self._tasks.append(task)
        self._save()

        # Start the process in a background thread
        thread = threading.Thread(target=self._run_task, args=(task_id, command))
        thread.daemon = True
        thread.start()

        return task

    def _run_task(self, task_id: str, command: str) -> None:
        """Run a task in a background thread."""
        output_path = self.tasks_dir / f"{task_id}.log"

        try:
            proc = subprocess.Popen(
                command,
                shell=True,
                stdout=open(output_path, "w", encoding="utf-8"),
                stderr=subprocess.STDOUT,
            )
            self._running_procs[task_id] = proc

            exit_code = proc.wait()
            self._running_procs.pop(task_id, None)

            # Update task status
            for task in self._tasks:
                if task.id == task_id:
                    task.status = "completed" if exit_code == 0 else "failed"
                    task.exit_code = exit_code
                    break
            self._save()

        except Exception as e:
            for task in self._tasks:
                if task.id == task_id:
                    task.status = "failed"
                    break
            self._save()

    def get(self, task_id: str) -> BackgroundTask | None:
        """Get a task by ID."""
        for task in self._tasks:
            if task.id == task_id:
                return task
        return None

    def list_all(self) -> list[BackgroundTask]:
        """List all tasks."""
        return sorted(self._tasks, key=lambda t: t.started_at, reverse=True)

    def list_active(self) -> list[BackgroundTask]:
        """List running tasks."""
        return [t for t in self._tasks if t.status == "running"]

    def read_output(self, task_id: str) -> str:
        """Read task output from log file."""
        task = self.get(task_id)
        if not task:
            return f"Task {task_id} not found"

        output_path = Path(task.output_path)
        if not output_path.exists():
            return "No output yet"

        try:
            return output_path.read_text(encoding="utf-8")
        except Exception as e:
            return f"Error reading output: {e}"

    def cancel(self, task_id: str) -> bool:
        """Cancel a running task."""
        proc = self._running_procs.get(task_id)
        if proc:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
            self._running_procs.pop(task_id, None)

        for task in self._tasks:
            if task.id == task_id:
                task.status = "cancelled"
                break
        self._save()
        return True

    def remove(self, task_id: str) -> bool:
        """Remove a task and its output."""
        task = self.get(task_id)
        if not task:
            return False

        # Cancel if running
        if task_id in self._running_procs:
            self.cancel(task_id)

        # Remove output file
        output_path = Path(task.output_path)
        if output_path.exists():
            output_path.unlink()

        # Remove from list
        self._tasks = [t for t in self._tasks if t.id != task_id]
        self._save()
        return True

    def clear_completed(self) -> int:
        """Remove all completed/failed tasks."""
        before = len(self._tasks)
        for task in list(self._tasks):
            if task.status in ("completed", "failed", "cancelled"):
                output_path = Path(task.output_path)
                if output_path.exists():
                    try:
                        output_path.unlink()
                    except Exception:
                        pass
                self._tasks.remove(task)
        self._save()
        return before - len(self._tasks)


# Global instance
task_manager = BackgroundTaskManager()