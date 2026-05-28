"""Hybrid thinking router — decides when to use <think> vs direct answers.

Classification heuristics (in priority order):
  1. Explicit override via slash command (/think, /fast)
  2. Task-type keyword matching
  3. Token budget heuristic
  4. Tool complexity heuristic
"""
from __future__ import annotations

import os
import platform
from pathlib import Path
from typing import Any

from draguniteus.config import DEFAULT_CONFIG_DIR


def _get_config_dir() -> Path:
    if platform.system() == "Windows":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path.home()
    return base / ".draguniteus"


# Task types that typically need deep thinking
REASONING_TASKS = frozenset([
    "analyze", "explain why", "debug", "investigate", "assess",
    "plan", "design", "architecture", "evaluate", "compare",
    "review", "understand", "figure out", "diagnose", "research",
    "why does", "how does", "what if", "assess", "synthesize",
    "investigate", "critique", "audit", "evaluate",
])

# Task types that are typically direct/fast
DIRECT_TASKS = frozenset([
    "write", "create", "add", "fix", "delete comment",
    "format", "simple question", "what is", "list", "show",
    "get", "fetch", "run", "execute", "build", "make",
    "delete", "remove", "rename", "move", "copy",
])

# Tools that suggest higher complexity (more likely to need thinking)
COMPLEX_TOOLS = frozenset([
    "Bash", "Edit", "MultiEdit", "Write", "Grep", "Glob",
    "Orchestrate", "Agent", "mcp__",
])


class ThinkingRouter:
    """Routes each turn to thinking or direct-answer mode."""

    def __init__(
        self,
        enabled: bool = True,
        token_budget_threshold: float = 0.6,
        complexity_tool_threshold: int = 3,
    ):
        self.enabled = enabled
        self.token_budget_threshold = token_budget_threshold  # % of context to trigger direct
        self.complexity_tool_threshold = complexity_tool_threshold

        # Per-session override flags (reset each turn)
        self._override: str | None = None  # "think" or "direct"

    def route(
        self,
        messages: list[dict[str, Any]],
        system: str = "",
        tools: list[dict[str, Any]] | None = None,
        context_tokens: int = 0,
        max_context_tokens: int = 204800,
    ) -> dict[str, Any]:
        """Decide thinking vs direct. Returns routing decision dict."""
        if not self.enabled:
            return {"thinking": False, "mode": "direct", "reason": "disabled"}

        # 1. Check override
        if self._override == "think":
            self._override = None
            return {"thinking": True, "mode": "forced_think", "reason": "explicit /think"}

        if self._override == "direct":
            self._override = None
            return {"thinking": False, "mode": "forced_direct", "reason": "explicit /fast"}

        # 2. Keyword-based routing
        if messages:
            last_user = ""
            for m in reversed(messages):
                if m.get("role") == "user":
                    last_user = m.get("content", "")
                    break

            user_lower = last_user.lower()

            for kw in REASONING_TASKS:
                if kw in user_lower:
                    return {"thinking": True, "mode": "keyword", "reason": f"matched '{kw}'"}

            for kw in DIRECT_TASKS:
                if kw in user_lower and len(last_user) < 200:
                    return {"thinking": False, "mode": "keyword", "reason": f"matched '{kw}' (direct)"}

        # 3. Token budget heuristic
        if max_context_tokens > 0:
            ratio = context_tokens / max_context_tokens
            if ratio > self.token_budget_threshold:
                # High context usage → skip thinking overhead, go direct
                return {"thinking": False, "mode": "token_budget", "reason": f"context {ratio:.0%} > threshold"}

        # 4. Tool complexity heuristic
        if tools and len(tools) > self.complexity_tool_threshold:
            # Many tools → likely complex task, enable thinking
            return {"thinking": True, "mode": "tool_complexity", "reason": f"{len(tools)} tools"}

        # 5. Default: thinking for ambiguous cases
        return {"thinking": True, "mode": "default", "reason": "no strong signal"}

    def set_override(self, mode: str) -> None:
        """Set a per-turn override: "think" or "direct"."""
        self._override = mode

    def compute_betas(
        self,
        base_betas: list[str],
        routing: dict[str, Any],
    ) -> list[str]:
        """Adjust betas based on routing decision.

        If thinking is enabled, ensure "thinking" or "interleaved-thinking"
        is in the betas list.
        """
        if not routing.get("thinking", False):
            return base_betas

        betas = list(base_betas)
        thinking_beta = "interleaved-thinking"

        if thinking_beta not in betas:
            betas = [thinking_beta] + betas

        return betas


# Global router instance
_thinking_router: ThinkingRouter | None = None


def get_thinking_router() -> ThinkingRouter:
    global _thinking_router
    if _thinking_router is None:
        _thinking_router = ThinkingRouter()
    return _thinking_router
