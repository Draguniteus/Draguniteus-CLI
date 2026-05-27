"""Tool reflection — tracks per-tool statistics for self-improvement.

Stores: call count, success rate, avg latency, failure reasons, last used.
File: ~/.draguniteus/tool_stats.json
"""
from __future__ import annotations

import json
import os
import platform
import time
from pathlib import Path
from typing import Any

from draguniteus.config import DEFAULT_CONFIG_DIR


def _get_config_dir() -> Path:
    if platform.system() == "Windows":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path.home()
    return base / ".draguniteus"


TOOL_STATS_FILE = _get_config_dir() / "tool_stats.json"


class ToolReflection:
    """Tracks per-tool execution statistics."""

    def __init__(self):
        self._stats: dict[str, dict[str, Any]] = {}
        self._active_calls: dict[str, float] = {}  # tool_name -> start_time
        self._load()

    def _load(self) -> None:
        """Load stats from disk."""
        if TOOL_STATS_FILE.exists():
            try:
                self._stats = json.loads(TOOL_STATS_FILE.read_text(encoding="utf-8"))
            except Exception:
                self._stats = {}

    def _save(self) -> None:
        """Persist stats to disk."""
        try:
            TOOL_STATS_FILE.parent.mkdir(parents=True, exist_ok=True)
            TOOL_STATS_FILE.write_text(json.dumps(self._stats, indent=2), encoding="utf-8")
        except Exception:
            pass

    def record_start(self, tool_name: str) -> None:
        """Record that a tool call started."""
        self._active_calls[tool_name] = time.time()

    def record_result(
        self,
        tool_name: str,
        success: bool,
        error: str = "",
    ) -> None:
        """Record the result of a tool call."""
        start_time = self._active_calls.pop(tool_name, None)
        latency_ms = int((time.time() - start_time) * 1000) if start_time else 0

        if tool_name not in self._stats:
            self._stats[tool_name] = {
                "call_count": 0,
                "success_count": 0,
                "failure_count": 0,
                "total_latency_ms": 0,
                "failure_reasons": {},
                "last_used": "",
            }

        stats = self._stats[tool_name]
        stats["call_count"] += 1
        if success:
            stats["success_count"] += 1
        else:
            stats["failure_count"] += 1
            reason = error[:80] if error else "unknown"
            stats["failure_reasons"][reason] = stats["failure_reasons"].get(reason, 0) + 1

        stats["total_latency_ms"] += latency_ms
        stats["last_used"] = time.strftime("%Y-%m-%d %H:%M:%S")
        stats["avg_latency_ms"] = stats["total_latency_ms"] / stats["call_count"]

        self._save()

    def get_stats(self, tool_name: str) -> dict[str, Any]:
        """Get statistics for a specific tool."""
        return self._stats.get(tool_name, {})

    def get_all_stats(self) -> dict[str, dict[str, Any]]:
        """Get all tool statistics."""
        return self._stats

    def get_least_reliable(self, min_calls: int = 3) -> list[tuple[str, float]]:
        """Return tools with lowest success rate (min calls to qualify)."""
        results = []
        for name, stats in self._stats.items():
            calls = stats.get("call_count", 0)
            if calls >= min_calls:
                rate = stats.get("success_count", 0) / calls
                results.append((name, rate))
        return sorted(results, key=lambda x: x[1])

    def get_slowest(self, min_calls: int = 3) -> list[tuple[str, float]]:
        """Return tools with highest avg latency (ms)."""
        results = []
        for name, stats in self._stats.items():
            calls = stats.get("call_count", 0)
            if calls >= min_calls:
                results.append((name, stats.get("avg_latency_ms", 0)))
        return sorted(results, key=lambda x: x[1], reverse=True)

    def format_summary(self) -> str:
        """Format a human-readable summary of tool stats."""
        if not self._stats:
            return "No tool statistics yet."

        lines = ["Tool Statistics:", "-" * 50]
        for name, stats in sorted(self._stats.items(), key=lambda x: x[1].get("call_count", 0), reverse=True):
            calls = stats.get("call_count", 0)
            success = stats.get("success_count", 0)
            rate = f"{success/calls*100:.0f}%" if calls else "N/A"
            avg_ms = stats.get("avg_latency_ms", 0)
            failures = stats.get("failure_count", 0)

            line = f"  {name}: {calls} calls, {rate} ok, avg {avg_ms:.0f}ms"
            if failures:
                line += f", {failures} failures"
            lines.append(line)

            # Show top failure reasons
            reasons = stats.get("failure_reasons", {})
            if reasons:
                top = sorted(reasons.items(), key=lambda x: x[1], reverse=True)[:2]
                for reason, count in top:
                    lines.append(f"    ✗ {reason[:60]} ({count}x)")

        return "\n".join(lines)


# Global reflection instance
_tool_reflection: ToolReflection | None = None


def get_tool_reflection() -> ToolReflection:
    global _tool_reflection
    if _tool_reflection is None:
        _tool_reflection = ToolReflection()
    return _tool_reflection
