"""Memory management: project memory (DRAGUNITEUS.md), daily notes, long-term, vector."""
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
    """Orchestrates short-term (session), medium-term (daily), long-term (DRAGUNITEUS.md).

    Also provides access to ChromaDB-backed vector memory via the vector_memory property.
    """

    def __init__(self):
        self.project_memory = ProjectMemory()
        self._vector_memory = None

    @property
    def vector_memory(self):
        """Lazy-init ChromaDB vector memory."""
        if self._vector_memory is None:
            try:
                from draguniteus.memory.vector_store import get_vector_memory
                self._vector_memory = get_vector_memory(Path.cwd())
            except Exception:
                self._vector_memory = None
        return self._vector_memory

    def load_for_agent(self, query: str | None = None) -> str:
        """Return all relevant memory as a string for injection into system prompt.

        Args:
            query: optional search query (e.g. last user message) used to
                    retrieve relevant memories from ChromaDB.
        """
        parts = []

        # Long-term
        pm = self.project_memory.read()
        if pm:
            parts.append(f"## Project Memory (DRAGUNITEUS.md)\n{pm}")

        # Today's daily
        daily = self.project_memory.read_daily()
        if daily:
            parts.append(f"## Today\n{daily}")

        # Vector memory: semantic search + count
        vm = self.vector_memory
        if vm is not None:
            try:
                count = vm.count()
                if count > 0:
                    if query:
                        # Retrieve top memories relevant to current task
                        results = vm.search(query, n_results=5)
                        if results:
                            mem_lines = [f"## Relevant Memories\n"]
                            for r in results:
                                snippet = r.get("content", "")[:300]
                                mem_lines.append(f"- [{r.get('type', 'general')}] {snippet}")
                            parts.append("\n".join(mem_lines))
                        parts.append(f"## Vector Memory\n{count} memories indexed")
                    else:
                        parts.append(f"## Vector Memory\n{count} memories indexed (use /memory search <query> to query)")
            except Exception:
                pass

        return "\n\n".join(parts) if parts else ""

    def search_vector_memory(self, query: str, n_results: int = 5) -> list[dict[str, Any]]:
        """Search the vector memory store."""
        vm = self.vector_memory
        if vm is None:
            return []
        try:
            return vm.search(query, n_results=n_results)
        except Exception:
            return []

    def add_to_vector_memory(
        self,
        content: str,
        doc_type: str = "general",
        path: str = "",
        tags: list[str] | None = None,
    ) -> str:
        """Add content to vector memory. Returns doc ID."""
        vm = self.vector_memory
        if vm is None:
            return ""
        try:
            return vm.add(content, doc_type=doc_type, path=path, tags=tags)
        except Exception:
            return ""


# Module-level singleton accessor
_memory_manager_instance: MemoryManager | None = None


def _get_memory_manager_singleton() -> "MemoryManager":
    global _memory_manager_instance
    if _memory_manager_instance is None:
        _memory_manager_instance = MemoryManager()
    return _memory_manager_instance


def _get_memory_manager() -> MemoryManager:
    return _get_memory_manager_singleton()


# Backward-compat global instance
memory_manager = _get_memory_manager_singleton()
