"""Memory management: project memory (DRAGUNITEUS.md), daily notes, long-term."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from draguniteus.config import Config


class ProjectMemory:
    """Manages DRAGUNITEUS.md — project-level persistent memory."""

    def __init__(self, project_dir: Path | None = None):
        self.project_dir = project_dir or Config.project_dir()
        self.memory_dir = self.project_dir / "memory"
        self.dragon_md = self.project_dir / "DRAGUNITEUS.md"

    def exists(self) -> bool:
        return self.dragon_md.exists()

    def read(self) -> str:
        if self.dragon_md.exists():
            return self.dragon_md.read_text(encoding="utf-8")
        return ""

    def write(self, content: str) -> None:
        self.dragon_md.parent.mkdir(parents=True, exist_ok=True)
        self.dragon_md.write_text(content, encoding="utf-8")

    def append_section(self, heading: str, content: str) -> None:
        """Append a new section to DRAGUNITEUS.md."""
        existing = self.read()
        new_section = f"\n\n## {heading}\n{content}\n"
        self.write(existing + new_section)

    def read_daily(self, date_str: str | None = None) -> str | None:
        """Read daily memory file (memory/YYYY-MM-DD.md)."""
        date = date_str or time.strftime("%Y-%m-%d")
        path = self.memory_dir / f"{date}.md"
        if path.exists():
            return path.read_text(encoding="utf-8")
        return None

    def write_daily(self, content: str, date_str: str | None = None) -> None:
        date = date_str or time.strftime("%Y-%m-%d")
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        path = self.memory_dir / f"{date}.md"
        path.write_text(content, encoding="utf-8")


class MemoryManager:
    """Orchestrates short-term (session), medium-term (daily), long-term (DRAGUNITEUS.md)."""

    def __init__(self):
        self.project_memory = ProjectMemory()

    def load_for_agent(self) -> str:
        """Return all relevant memory as a string for injection into system prompt."""
        parts = []

        # Long-term
        pm = self.project_memory.read()
        if pm:
            parts.append(f"## Project Memory (DRAGUNITEUS.md)\n{pm}")

        # Today's daily
        daily = self.project_memory.read_daily()
        if daily:
            parts.append(f"## Today\n{daily}")

        return "\n\n".join(parts) if parts else ""


# Global instance
memory_manager = MemoryManager()