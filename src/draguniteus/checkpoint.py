"""Checkpoint system for long-running agent autonomy.

Saves agent state to .draguniteus/checkpoints/<session_id>/step_<N>.json
with atomic writes (temp file + rename) — safe on Windows and POSIX.
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any

from draguniteus.config import DEFAULT_CONFIG_DIR


def _get_config_dir() -> Path:
    if platform.system() == "Windows":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path.home()
    return base / ".draguniteus"


@dataclass
class AgentCheckpoint:
    """Serializable snapshot of agent state at a point in time."""
    session_id: str
    step_count: int
    phase: str = "executing"
    messages: list[dict[str, Any]] = field(default_factory=list)
    system: str = ""
    pending_tool_calls: list[dict[str, Any]] | None = None
    workflow_state: dict[str, Any] | None = None
    tracked_files: list[str] = field(default_factory=list)
    effort: str = "medium"
    model: str = "MiniMax-M2.7"
    created_at: str = ""
    # Truncate messages to last N turns to avoid huge checkpoints
    max_message_turns: int = 50

    def __post_init__(self):
        if not self.created_at:
            import datetime
            self.created_at = datetime.datetime.now().isoformat()
        # Truncate old messages
        if len(self.messages) > self.max_message_turns * 2:
            # Keep system + last N turns
            system_msgs = [m for m in self.messages if m.get("role") == "system"]
            non_system = [m for m in self.messages if m.get("role") != "system"]
            self.messages = system_msgs + non_system[-self.max_message_turns:]


class CheckpointManager:
    """Manages checkpoint lifecycle — save, load, list, resume."""

    def __init__(self, checkpoint_dir: Path | None = None, checkpoint_every: int = 5):
        self.base_dir = checkpoint_dir or (_get_config_dir() / "checkpoints")
        self.checkpoint_every = checkpoint_every
        self._current_session: str | None = None
        self._step_count: int = 0

    def session_dir(self, session_id: str) -> Path:
        return self.base_dir / session_id

    def save(self, checkpoint: AgentCheckpoint) -> Path:
        """Save checkpoint atomically (write to .tmp, then rename)."""
        sess_dir = self.session_dir(checkpoint.session_id)
        sess_dir.mkdir(parents=True, exist_ok=True)

        step_file = sess_dir / f"step_{checkpoint.step_count:04d}.json"
        tmp_file = sess_dir / f"step_{checkpoint.step_count:04d}.json.tmp"

        data = asdict(checkpoint)
        # Write to tmp first
        tmp_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        # Atomic rename (works on Windows since Python 3.2)
        tmp_file.replace(step_file)

        # Prune old checkpoints — keep last 20
        self._prune_old(checkpoint.session_id, keep=20)

        return step_file

    def _prune_old(self, session_id: str, keep: int = 20) -> None:
        """Remove oldest checkpoints, keeping the most recent N."""
        sess_dir = self.session_dir(session_id)
        if not sess_dir.exists():
            return
        checkpoints = sorted(
            sess_dir.glob("step_*.json"),
            key=lambda p: p.stat().st_mtime,
        )
        for old in checkpoints[:-keep]:
            try:
                old.unlink()
            except Exception:
                pass

    def load(self, session_id: str, step: int) -> AgentCheckpoint | None:
        """Load a specific step checkpoint."""
        path = self.session_dir(session_id) / f"step_{step:04d}.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return AgentCheckpoint(**data)
        except Exception:
            return None

    def load_latest(self, session_id: str) -> AgentCheckpoint | None:
        """Load the most recent checkpoint for a session."""
        sess_dir = self.session_dir(session_id)
        if not sess_dir.exists():
            return None
        checkpoints = sorted(
            sess_dir.glob("step_*.json"),
            key=lambda p: p.stat().st_mtime,
        )
        if not checkpoints:
            return None
        return self.load(session_id, int(checkpoints[-1].stem.split("_")[1]))

    def list_checkpoints(self, session_id: str) -> list[dict[str, Any]]:
        """List all checkpoints for a session (metadata only, no full load)."""
        sess_dir = self.session_dir(session_id)
        if not sess_dir.exists():
            return []
        result = []
        for p in sorted(sess_dir.glob("step_*.json"), key=lambda p: p.stat().st_mtime):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                result.append({
                    "step": data.get("step_count", int(p.stem.split("_")[1])),
                    "phase": data.get("phase", "unknown"),
                    "message_count": len(data.get("messages", [])),
                    "created_at": data.get("created_at", ""),
                    "path": str(p),
                })
            except Exception:
                continue
        return result

    def delete_session(self, session_id: str) -> None:
        """Delete all checkpoints for a session."""
        sess_dir = self.session_dir(session_id)
        if sess_dir.exists():
            shutil.rmtree(sess_dir, ignore_errors=True)

    def start_session(self, session_id: str, checkpoint_every: int = 5) -> None:
        """Begin a new session with checkpoint tracking."""
        self._current_session = session_id
        self._step_count = 0
        self.checkpoint_every = checkpoint_every

    def tick(self) -> int:
        """Increment step count. Returns new count."""
        self._step_count += 1
        return self._step_count

    def should_checkpoint(self) -> bool:
        """True if it's time to save a checkpoint."""
        return self._step_count > 0 and self._step_count % self.checkpoint_every == 0

    @property
    def current_session(self) -> str | None:
        return self._current_session

    @property
    def current_step(self) -> int:
        return self._step_count


# Global instance
_checkpoint_manager: CheckpointManager | None = None


def get_checkpoint_manager() -> CheckpointManager:
    global _checkpoint_manager
    if _checkpoint_manager is None:
        _checkpoint_manager = CheckpointManager()
    return _checkpoint_manager
