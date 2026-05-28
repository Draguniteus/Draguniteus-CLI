"""Developer role adapter — injects structured developer context into each turn.

MiniMax API supports a 'developer' role message type. This builds a concise
developer message from: active file context, tools summary, project constraints,
and current task mode.
"""
from __future__ import annotations

import platform
from pathlib import Path
from typing import Any

MAX_DEVELOPER_TOKENS = 2048


def _get_config_dir() -> Path:
    if platform.system() == "Windows":
        base = Path(platform.os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path.home()
    return base / ".draguniteus"


class RoleAdapter:
    """Builds and manages developer-role messages for the API."""

    def __init__(self, enabled: bool = True, max_tokens: int = MAX_DEVELOPER_TOKENS):
        self.enabled = enabled
        self.max_tokens = max_tokens
        self._tracked_files: list[str] = []
        self._active_mode: str = "default"
        self._project_constraints: str = ""

    def set_tracked_files(self, files: list[str]) -> None:
        self._tracked_files = list(files)

    def set_active_mode(self, mode: str) -> None:
        self._active_mode = mode

    def set_project_constraints(self, constraints: str) -> None:
        self._project_constraints = constraints

    def build_developer_message(
        self,
        tools_summary: str = "",
        recent_tool_results: list[str] | None = None,
    ) -> str:
        """Build the developer role message content."""
        if not self.enabled:
            return ""

        parts = []

        if self._active_mode != "default":
            parts.append(f"[Mode: {self._active_mode.upper()}]")

        if self._tracked_files:
            files_short = [Path(f).name for f in self._tracked_files[-5:]]
            parts.append(f"Active files: {', '.join(files_short)}")

        if self._project_constraints:
            const_short = self._truncate(self._project_constraints, 300)
            parts.append(f"Project constraints:\n{const_short}")

        if tools_summary:
            parts.append(f"Available tools: {self._truncate(tools_summary, 400)}")

        if recent_tool_results:
            results_short = self._summarize_results(recent_tool_results)
            if results_short:
                parts.append(f"Recent results:\n{results_short}")

        content = "\n\n".join(parts) if parts else ""
        return self._truncate(content, self.max_tokens)

    def build_developer_message_for_turn(
        self,
        messages: list[dict[str, Any]] | None = None,
        tools: list[dict[str, Any]] | None = None,
        tracked_files: list[str] | None = None,
        mode: str = "default",
        recent_tool_results: list[dict[str, Any]] | None = None,
    ) -> str:
        """Build developer message for a turn."""
        if not self.enabled:
            return ""

        if tracked_files:
            self.set_tracked_files(tracked_files)
        if mode != "default":
            self.set_active_mode(mode)

        tools_summary = ""
        if tools:
            tool_names = [t.get("name", "?") for t in tools[:20]]
            tools_summary = ", ".join(tool_names)

        tool_result_strs = None
        if recent_tool_results:
            tool_result_strs = []
            for tr in recent_tool_results:
                success = tr.get("success", True)
                error = tr.get("error", "")
                name = tr.get("name", "?")
                if success:
                    tool_result_strs.append(f"{name}: ok")
                else:
                    tool_result_strs.append(f"{name}: FAILED — {error[:100]}")

        return self.build_developer_message(
            tools_summary=tools_summary,
            recent_tool_results=tool_result_strs,
        )

    def summarize_tool_results(self, tool_results: list[dict[str, Any]]) -> str:
        if not tool_results:
            return ""

        summaries = []
        for tr in tool_results[-5:]:
            tool_name = tr.get("name", "?")
            success = tr.get("success", True)
            error = tr.get("error", "")
            if success:
                summaries.append(f"  {tool_name}: ok")
            else:
                summaries.append(f"  {tool_name}: FAILED — {error[:100]}")

        return "\n".join(summaries) if summaries else ""

    @staticmethod
    def _truncate(text: str, max_chars: int) -> str:
        if len(text) <= max_chars:
            return text
        return text[:max_chars - 3] + "..."

    @staticmethod
    def _summarize_results(results: list[str]) -> str:
        if not results:
            return ""
        last = str(results[-1]) if results else ""
        return last[:200]


_role_adapter: RoleAdapter | None = None


def get_role_adapter() -> RoleAdapter:
    global _role_adapter
    if _role_adapter is None:
        _role_adapter = RoleAdapter()
    return _role_adapter