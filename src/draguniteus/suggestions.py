"""Prompt suggestions: grayed example commands based on git history."""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any


class PromptSuggestions:
    """Manages prompt suggestions based on git history and conversation."""

    def __init__(self):
        self.enabled = True
        self.history_file = Path.home() / ".draguniteus" / "suggestions_history.json"
        self._suggestions: list[str] = []
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
                # Use recent commit messages as suggestions
                lines = [l.strip() for l in result.stdout.strip().split('\n') if l.strip()]
                # Truncate long messages and filter to reasonable length
                self._suggestions = [l[:60] for l in lines[:5]] if lines else []
        except Exception:
            self._suggestions = []

    def get_suggestion(self) -> str | None:
        """Get the current suggestion for the prompt."""
        if not self.enabled:
            return None
        if self._suggestions:
            return self._suggestions[0]
        return None

    def refresh_from_git(self) -> None:
        """Refresh suggestions from git history."""
        self._load_default()

    def disable(self) -> None:
        """Disable suggestions."""
        self.enabled = False

    def enable(self) -> None:
        """Enable suggestions."""
        self.enabled = True


# Global instance
prompt_suggestions = PromptSuggestions()