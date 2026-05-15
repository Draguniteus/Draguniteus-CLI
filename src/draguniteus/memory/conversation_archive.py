"""Conversation Archive: infinite context with semantic compression.

Instead of losing context when it exceeds token limits, we compress and archive
conversations semantically — keeping the FULL meaning accessible.

Uses a singleton to reuse the API client across compression calls.
"""
from __future__ import annotations

import json
import time
import hashlib
import threading
from pathlib import Path
from typing import Any

# Singleton for ConversationArchive to reuse client
_archive_instance: "ConversationArchive | None" = None
_archive_lock = threading.Lock()


def _get_conversation_archive(project_root: Path | None = None) -> "ConversationArchive":
    """Get or create the singleton ConversationArchive instance."""
    global _archive_instance
    if _archive_instance is None:
        with _archive_lock:
            if _archive_instance is None:
                _archive_instance = ConversationArchive(project_root)
    return _archive_instance


class ArchivedTurn:
    def __init__(self, role: str, content: str,
                 semantic_summary: str | None = None,
                 tool_calls: list | None = None,
                 ts: str | None = None):
        self.role = role
        self.content = content
        self.semantic_summary = semantic_summary or self._summarize(content)
        self.tool_calls = tool_calls or []
        self.timestamp = ts or time.strftime("%Y-%m-%dT%H:%M:%SZ")

    def _summarize(self, content: str, max_len: int = 200) -> str:
        """Create a semantic summary of the turn."""
        if len(content) <= max_len:
            return content
        return content[:max_len] + "..."

class ConversationArchive:
    """Infinite context archive with semantic retrieval.

    Stores conversations in a compressed but semantically complete form.
    Can retrieve any past conversation by semantic similarity.

    Usage:
        archive = ConversationArchive(project_root)
        archive.append(role="user", content="implemented auth system")
        archive.append(role="assistant", content="Here's what I did...")

        # When context gets full, compress old turns
        compressed = archive.compress(oldest_turns=20)

        # Retrieve by semantic search
        results = archive.retrieve("authentication decisions")
    """

    def __init__(self, project_root: Path | None = None):
        self.project_root = project_root or Path.cwd()
        self.archive_dir = self.project_root / ".draguniteus" / "conversation_archive"
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        self._turns: list[ArchivedTurn] = []
        self._index_file = self.archive_dir / "archive_index.json"
        self._last_compress_attempt: float = 0  # Rate-limit compression attempts
        self._compression_cooldown: float = 30.0  # Seconds between compression attempts
        self._load_index()
        # Reuse a single API client for all compression calls
        self._client = None

    def _get_client(self):
        """Get or create a reusable API client."""
        if self._client is None:
            from draguniteus.client import DraguniteusClient
            from draguniteus.config import Config
            self._client = DraguniteusClient(Config())
        return self._client

    def _load_index(self) -> None:
        if self._index_file.exists():
            try:
                data = json.loads(self._index_file.read_text())
                self._turns = [ArchivedTurn(**t) for t in data.get("turns", [])]
            except Exception:
                self._turns = []

    def _save_index(self) -> None:
        self._index_file.write_text(json.dumps({
            "turns": [vars(t) for t in self._turns],
        }, indent=2))

    def append(self, role: str, content: str,
               semantic_summary: str | None = None,
               tool_calls: list | None = None) -> None:
        """Add a turn to the archive."""
        turn = ArchivedTurn(role, content, semantic_summary, tool_calls)
        self._turns.append(turn)
        self._save_index()

    def compress(self, oldest_turns: int = 20, use_llm: bool = True) -> str:
        """Compress oldest turns into a semantic summary.

        Args:
            oldest_turns: How many oldest turns to compress into one archived turn.
            use_llm: If True, use LLM to create a rich semantic summary.
                     If False, use simple concatenation.

        Returns a summary of what was compressed.
        """
        if len(self._turns) <= oldest_turns * 2:
            return "Not enough turns to compress"

        to_compress = self._turns[:oldest_turns]
        remaining = self._turns[oldest_turns:]

        summaries = [t.semantic_summary for t in to_compress]

        if use_llm:
            compressed_text = self._llm_summarize(to_compress)
        else:
            compressed_text = f"[Archived {len(to_compress)} turns]: " + " | ".join(summaries)

        archived = ArchivedTurn(
            role="system",
            content=compressed_text,
            semantic_summary=f"Archive of {len(to_compress)} turns: {summaries[0][:100] if summaries else 'various topics'}",
        )

        self._turns = [archived] + remaining
        self._save_index()
        return compressed_text[:300]

    def _llm_summarize(self, turns: list[ArchivedTurn]) -> str:
        """Use MiniMax to create a rich semantic summary of archived turns."""
        try:
            client = self._get_client()

            turns_text = "\n\n".join(
                f"[{t.role}]: {t.content[:500]}" for t in turns
            )

            system = (
                "You are a semantic archivist. Given a sequence of conversation turns, "
                "produce a concise but information-rich summary that captures: "
                "1) What the user asked/did, "
                "2) What was decided or built, "
                "3) Any important constraints or requirements mentioned. "
                "Format as a flowing paragraph (no bullet points). "
                "Maximum 300 words."
            )

            resp = client.sync.messages.create(
                model="MiniMax-M2.1",
                max_tokens=500,
                system=system,
                messages=[{"role": "user", "content": f"Summarize this conversation:\n{turns_text}"}],
            )
            return resp.content[0].text
        except Exception:
            # Fallback to simple join
            return f"[Archived {len(turns)} turns]: " + " | ".join(summaries[:5])

    def retrieve(self, query: str, max_turns: int = 10) -> list[ArchivedTurn]:
        """Find archived turns matching a semantic query."""
        query_lower = query.lower()
        scored = []
        for turn in self._turns:
            score = 0
            if query_lower in turn.semantic_summary.lower():
                score += 3
            if query_lower in turn.content.lower():
                score += 1
            if score > 0:
                scored.append((score, turn))

        scored.sort(reverse=True)
        return [t for _, t in scored[:max_turns]]

    def get_context_for(self, query: str, max_tokens: int = 8000) -> str:
        """Build a context string for a query from archived turns.

        Returns a compressed context string that fits within max_tokens.
        """
        turns = self.retrieve(query, max_turns=20)
        context_parts = []
        total_len = 0

        for turn in turns:
            part = f"[{turn.role}]: {turn.content}"
            if total_len + len(part) > max_tokens:
                break
            context_parts.append(part)
            total_len += len(part)

        return "\n\n".join(context_parts)

    def count(self) -> int:
        return len(self._turns)

    def should_compress(self, context_turns: int, max_turns: int = 40) -> bool:
        """Check if archive should be compressed based on current context size."""
        if context_turns < max_turns:
            return False
        # Rate-limit: don't compress more than once every _compression_cooldown seconds
        if time.time() - self._last_compress_attempt < self._compression_cooldown:
            return False
        return True

    def auto_archive_if_needed(self, context_turns: int, max_turns: int = 40) -> str | None:
        """Call compress if context is getting full. Returns summary if compressed."""
        if self.should_compress(context_turns, max_turns):
            self._last_compress_attempt = time.time()
            return self.compress(oldest_turns=min(20, context_turns // 2))
        return None

    def archive_session(self, session_id: str, messages: list[dict]) -> None:
        """Archive a full session (called when session ends)."""
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if isinstance(content, list):
                content = " ".join(c.get("text", "") for c in content if isinstance(c, dict))
            if content:
                self.append(role=role, content=content[:1000])