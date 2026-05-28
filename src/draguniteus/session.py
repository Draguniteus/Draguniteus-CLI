"""Session management: JSONL transcripts, sessions index, continue/resume."""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from draguniteus.config import Config


@dataclass
class Session:
    id: str
    created_at: str
    last_updated: str
    model: str
    working_dir: str
    transcript_path: str
    notes: list[str] | None = None
    branch_from: str | None = None  # session_id this was branched from
    branch_name: str | None = None  # name of this branch
    parent_id: str | None = None    # direct parent session (None if root)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SessionStore:
    """Manages session index and JSONL transcript files."""

    def __init__(self, config: Config | None = None):
        self.config = config or Config()
        self.sessions_path = self.config.session_dir / "sessions.json"
        self.transcripts_dir = self.config.session_dir / "transcripts"
        self.transcripts_dir.mkdir(parents=True, exist_ok=True)
        self._sessions: list[Session] = []
        self._load()

    def _load(self) -> None:
        if self.sessions_path.exists():
            try:
                with open(self.sessions_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # Handle both {"sessions": [...]} and [...] formats
                    if isinstance(data, dict):
                        sessions_list = data.get("sessions", [])
                    else:
                        sessions_list = data
                    self._sessions = [Session(**s) for s in sessions_list]
            except (json.JSONDecodeError, ValueError, TypeError):
                # Corrupt or empty sessions.json — start fresh
                self._sessions = []
        else:
            self._sessions = []

    def _save(self) -> None:
        self.sessions_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.sessions_path, "w", encoding="utf-8") as f:
            json.dump([s.to_dict() for s in self._sessions], f, indent=2)

    def create(self, model: str) -> Session:
        sid = f"sess_{uuid.uuid4().hex[:12]}"
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        session = Session(
            id=sid,
            created_at=now,
            last_updated=now,
            model=model,
            working_dir=str(Path.cwd()),
            transcript_path=str(self.transcripts_dir / f"{sid}.jsonl"),
        )
        self._sessions.append(session)
        self._save()
        return session

    def get(self, session_id: str) -> Session | None:
        for s in self._sessions:
            if s.id == session_id:
                return s
        return None

    def get_or_create(self, model: str) -> Session:
        """Get the most recent session for current working dir, or create new."""
        cwd = str(Path.cwd())
        # Find most recent for this dir
        for s in reversed(self._sessions):
            if s.working_dir == cwd:
                s.last_updated = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                self._save()
                return s
        return self.create(model)

    def update(self, session: Session) -> None:
        session.last_updated = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self._save()

    def list_all(self) -> list[Session]:
        return sorted(self._sessions, key=lambda s: s.last_updated, reverse=True)

    def append_event(self, session: Session, event: dict[str, Any]) -> None:
        """Append a JSONL event to the transcript."""
        transcript_path = Path(session.transcript_path)
        with open(transcript_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

    def branch_session(self, session_id: str, branch_name: str, model: str | None = None) -> Session | None:
        """Create a new branch from an existing session.

        The new session retains a link to its parent (branch_from).
        Useful for exploring alternative approaches without losing the original path.
        """
        parent = self.get(session_id)
        if not parent:
            return None

        sid = f"sess_{uuid.uuid4().hex[:12]}"
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        # New transcript for the branch
        new_transcript_path = str(self.transcripts_dir / f"{sid}.jsonl")

        branch = Session(
            id=sid,
            created_at=now,
            last_updated=now,
            model=model or parent.model,
            working_dir=str(Path.cwd()),
            transcript_path=new_transcript_path,
            notes=[f" branched from {session_id}"],
            branch_from=session_id,
            branch_name=branch_name,
            parent_id=session_id,
        )
        self._sessions.append(branch)
        self._save()

        # Copy parent's transcript to new session (preserving history)
        parent_transcript = Path(parent.transcript_path)
        if parent_transcript.exists():
            try:
                content = parent_transcript.read_text(encoding="utf-8")
                new_transcript = Path(new_transcript_path)
                new_transcript.write_text(content, encoding="utf-8")
            except Exception:
                pass

        return branch

    def get_branch_children(self, session_id: str) -> list["Session"]:
        """Get all sessions that were branched from this session."""
        return [s for s in self._sessions if s.branch_from == session_id]

    def get_ancestors(self, session_id: str) -> list["Session"]:
        """Get the full ancestor chain of a session (root to parent)."""
        ancestors = []
        current = self.get(session_id)
        while current and current.parent_id:
            parent = self.get(current.parent_id)
            if parent:
                ancestors.append(parent)
                current = parent
            else:
                break
        return list(reversed(ancestors))

    def load_transcript(self, session: Session) -> list[dict[str, Any]]:
        """Load full transcript for a session."""
        path = Path(session.transcript_path)
        if not path.exists():
            return []
        events = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    events.append(json.loads(line))
        return events