"""Prompt suggestions and history management for Draguniteus REPL."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from draguniteus.config import DEFAULT_CONFIG_DIR


class HistoryManager:
    """Manages command history with per-project and global history."""

    def __init__(self):
        self.history_dir = DEFAULT_CONFIG_DIR / "history"
        self.history_dir.mkdir(parents=True, exist_ok=True)
        self._session_history: list[str] = []
        self._project_history: list[str] = []
        self._global_history: list[str] = []
        self._load_histories()

    def _load_histories(self) -> None:
        """Load history from disk."""
        project_key = str(hash(str(Path.cwd())))
        project_file = self.history_dir / f"project_{project_key}.json"
        if project_file.exists():
            try:
                self._project_history = json.loads(project_file.read_text())
            except Exception:
                self._project_history = []

        global_file = self.history_dir / "global.json"
        if global_file.exists():
            try:
                self._global_history = json.loads(global_file.read_text())
            except Exception:
                self._global_history = []

    def _save_histories(self) -> None:
        """Save histories to disk."""
        project_key = str(hash(str(Path.cwd())))
        project_file = self.history_dir / f"project_{project_key}.json"
        project_file.write_text(json.dumps(self._project_history[-1000:]))

        global_file = self.history_dir / "global.json"
        global_file.write_text(json.dumps(self._global_history[-1000:]))

    def add(self, command: str) -> None:
        """Add a command to history."""
        if command.strip() and (not self._session_history or command != self._session_history[-1]):
            self._session_history.append(command)
            self._project_history.append(command)
            self._global_history.append(command)
            self._save_histories()

    def search(self, query: str, scope: str = "session") -> list[str]:
        """Search history for commands matching query."""
        if scope == "session":
            history = self._session_history
        elif scope == "project":
            history = self._project_history
        else:
            history = self._global_history

        results = []
        for cmd in reversed(history):
            if query.lower() in cmd.lower():
                results.append(cmd)
        return results[:20]

    def interactive_search(self) -> str | None:
        """Interactive reverse history search (Ctrl+R) with character-by-character input.
        Returns the selected command or None if cancelled.
        """
        import sys

        try:
            import tty
            import termios
        except ImportError:
            return None

        all_history = list(self._global_history[-500:])
        if not all_history:
            return None

        search_query = ""
        matches: list[tuple[int, str]] = []
        current_match_idx = 0

        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)

        try:
            tty.setraw(fd)

            sys.stdout.write("\r\n")
            sys.stdout.write("\033[7m(reverse-i-search)`-\033[0m ")
            sys.stdout.flush()

            while True:
                ch = sys.stdin.read(1)

                if ch == "\x1b":  # Escape sequence
                    seq = ch + sys.stdin.read(2)
                    if seq == "\x1b[A":  # Up arrow
                        if matches and current_match_idx > 0:
                            current_match_idx -= 1
                            _, cmd = matches[current_match_idx]
                            sys.stdout.write("\r" + " " * 80 + "\r")
                            sys.stdout.write(f"\033[7m(reverse-i-search)`{search_query}\033[0m: {cmd}")
                            sys.stdout.flush()
                    elif seq == "\x1b[B":  # Down arrow
                        if matches and current_match_idx < len(matches) - 1:
                            current_match_idx += 1
                            _, cmd = matches[current_match_idx]
                            sys.stdout.write("\r" + " " * 80 + "\r")
                            sys.stdout.write(f"\033[7m(reverse-i-search)`{search_query}\033[0m: {cmd}")
                            sys.stdout.flush()
                    continue

                if ch == "\r" or ch == "\n":  # Enter
                    sys.stdout.write("\r\n")
                    if matches and 0 <= current_match_idx < len(matches):
                        return matches[current_match_idx][1]
                    return search_query if search_query else None

                if ch == "\x7f" or ch == "\x08":  # Backspace
                    if search_query:
                        search_query = search_query[:-1]
                        matches = [(i, cmd) for i, cmd in enumerate(all_history)
                                   if search_query.lower() in cmd.lower()]
                        current_match_idx = len(matches) - 1 if matches else 0
                        sys.stdout.write("\r" + " " * 80 + "\r")
                        if matches:
                            sys.stdout.write(f"\033[7m(reverse-i-search)`{search_query}\033[0m: {matches[current_match_idx][1]}")
                        else:
                            sys.stdout.write(f"\033[7m(reverse-i-search)`{search_query}\033[0m ")
                        sys.stdout.flush()
                    continue

                if ch == "\x03":  # Ctrl+C
                    sys.stdout.write("\r\n")
                    return None

                if ch == "\x12":  # Ctrl+R - cycle next match
                    if matches and len(matches) > 1:
                        current_match_idx = (current_match_idx + 1) % len(matches)
                        _, cmd = matches[current_match_idx]
                        sys.stdout.write("\r" + " " * 80 + "\r")
                        sys.stdout.write(f"\033[7m(reverse-i-search)`{search_query}\033[0m: {cmd}")
                        sys.stdout.flush()
                    continue

                if ch == "\x09":  # Tab - accept current match
                    if matches:
                        sys.stdout.write("\r\n")
                        return matches[current_match_idx][1]
                    continue

                if ch == "\x1b":  # Escape - cancel
                    sys.stdout.write("\r\n")
                    return None

                # Regular character
                search_query += ch
                matches = [(i, cmd) for i, cmd in enumerate(all_history)
                           if search_query.lower() in cmd.lower()]
                current_match_idx = len(matches) - 1 if matches else 0

                sys.stdout.write("\r" + " " * 80 + "\r")
                if matches:
                    sys.stdout.write(f"\033[7m(reverse-i-search)`{search_query}\033[0m: {matches[current_match_idx][1]}")
                else:
                    sys.stdout.write(f"\033[7m(reverse-i-search)`{search_query}\033[0m ")
                sys.stdout.flush()

        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

    def get_session_history(self) -> list[str]:
        """Get current session history."""
        return list(self._session_history)

    def clear_session(self) -> None:
        """Clear session history."""
        self._session_history = []


# Global history manager
_history_manager: HistoryManager | None = None


def get_history_manager() -> HistoryManager:
    global _history_manager
    if _history_manager is None:
        _history_manager = HistoryManager()
    return _history_manager


class PromptSuggestions:
    """Manages prompt suggestions based on git history and conversation."""

    def __init__(self):
        self.enabled = True
        self._suggestions: list[str] = []
        self._current_index = 0
        self._load_default()

    def _load_default(self) -> None:
        """Load default suggestions from recent git history."""
        self._suggestions = []
        try:
            result = subprocess.run(
                ["git", "log", "--oneline", "-10", "--pretty=format:%s"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                lines = [l.strip() for l in result.stdout.strip().split('\n') if l.strip()]
                self._suggestions = [l[:60] for l in lines[:5]] if lines else []
        except Exception:
            self._suggestions = ["help me with this task", "show me what we are working on"]

    def get_suggestion(self) -> str | None:
        """Get the current suggestion for the prompt."""
        if not self.enabled or not self._suggestions:
            return None
        return self._suggestions[self._current_index % len(self._suggestions)]

    def next(self) -> str | None:
        """Cycle to next suggestion."""
        if self._suggestions:
            self._current_index = (self._current_index + 1) % len(self._suggestions)
            return self.get_suggestion()
        return None

    def disable(self) -> None:
        """Disable suggestions."""
        self.enabled = False

    def enable(self) -> None:
        """Enable suggestions."""
        self.enabled = True

    def update_from_conversation(self, messages: list[dict]) -> None:
        """Update suggestions based on recent conversation context."""
        if not messages:
            return
        recent_topics = []
        for m in messages[-5:]:
            if m.get("role") == "user":
                content = m.get("content", "")
                if content and len(content) > 5:
                    recent_topics.append(content[:50])
        if recent_topics:
            self._suggestions = recent_topics[:3] + self._suggestions[:2]


# Global prompt suggestions
prompt_suggestions = PromptSuggestions()