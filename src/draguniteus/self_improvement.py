"""Self-improvement engine: meta-critique after each task.

After stream_one_turn completes with is_final=True, the
SelfImprovementEngine critiques the solution and updates:
  - SemanticGraph (add_decision with lessons learned)
  - PatternLibrary (learn from tool sequences)
  - MemoryManager (write_daily with improvement notes)
"""
from __future__ import annotations

from typing import Any

from draguniteus.theming import CYAN, DIM, GREEN, RESET


class SelfImprovementEngine:
    """Meta-critique engine — learns from completed tasks."""

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self._last_critique: str = ""

    def critique(
        self,
        task_description: str,
        tool_results: list[dict[str, Any]],
        messages: list[dict[str, Any]],
        outcome: str = "success",
    ) -> str:
        """Analyze a completed task and return a critique string.

        Args:
            task_description: what was asked to do
            tool_results: list of {name, success, error, result} dicts
            messages: full message history for the turn
            outcome: "success", "partial", or "failed"

        Returns:
            A critique string describing what went well, what didn't,
            and recommendations for next time.
        """
        if not self.enabled:
            return ""

        lines = []
        lines.append(f"[Self-Critique] Task: {task_description}")
        lines.append(f"Outcome: {outcome}")

        # Analyze tool usage patterns
        tool_names = [tr.get("name", "?") for tr in tool_results]
        successes = [tr for tr in tool_results if tr.get("success", True)]
        failures = [tr for tr in tool_results if not tr.get("success", True)]

        lines.append(f"Tools used: {', '.join(tool_names)}")
        lines.append(f"Success rate: {len(successes)}/{len(tool_results)}")

        if failures:
            lines.append("\nFailures:")
            for f in failures:
                lines.append(f"  - {f.get('name', '?')}: {f.get('error', 'unknown error')[:100]}")

        # What went well
        if successes and len(successes) == len(tool_results):
            lines.append("\n[OK] All tools succeeded on first try.")

        # Recommendations
        recommendations = self._generate_recommendations(tool_names, failures, outcome)
        if recommendations:
            lines.append("\nRecommendations:")
            for r in recommendations:
                lines.append(f"  • {r}")

        critique = "\n".join(lines)
        self._last_critique = critique

        # Actually update memory systems
        self.update_memory(task_description, tool_results, critique, outcome)

        return critique

    def _generate_recommendations(
        self,
        tool_names: list[str],
        failures: list[dict[str, Any]],
        outcome: str,
    ) -> list[str]:
        """Generate recommendations based on what happened."""
        recs = []

        if outcome == "failed":
            recs.append("Consider breaking this task into smaller steps next time.")
            recs.append("Try using more explicit tool descriptions in Edit calls.")

        if any("Edit" in t for t in tool_names) and failures:
            recs.append("When Edit fails, try Write as a fallback to overwrite the file.")

        if len(tool_names) > 10:
            recs.append("Large number of tools used — consider if a more direct approach exists.")

        if any("Bash" in t for t in tool_names):
            recs.append("Bash commands can be fragile — prefer native tools where possible.")

        if not failures and outcome == "success" and len(tool_names) <= 3:
            recs.append("Efficient execution — minimal tool calls for this task.")

        return recs

    def update_memory(
        self,
        task_description: str,
        tool_results: list[dict[str, Any]],
        critique: str,
        outcome: str,
    ) -> None:
        """Update semantic graph, pattern library, and daily memory."""
        try:
            # Update SemanticGraph with decision
            try:
                from draguniteus.memory.semantic_graph import _get_semantic_graph
                graph = _get_semantic_graph()
                decision = f"Task: {task_description}\nOutcome: {outcome}\nCritique: {critique[:200]}"
                graph.add_decision(task_description, decision, ["self-improvement", outcome])
            except Exception:
                pass

            # Update PatternLibrary from tool sequence
            if outcome == "success":
                try:
                    from draguniteus.memory.pattern_library import _get_pattern_library
                    library = _get_pattern_library()
                    tool_names = [tr.get("name", "?") for tr in tool_results]
                    library.learn_from_tool_sequence(tool_names, success=True)
                except Exception:
                    pass

            # Write daily improvement note
            try:
                from draguniteus.memory.manager import _get_memory_manager
                mgr = _get_memory_manager()
                note = f"[Self-Improvement] {task_description[:80]}\n{critique[:300]}"
                mgr.write_daily(note)
            except Exception:
                pass

        except Exception:
            pass

    @property
    def last_critique(self) -> str:
        """Return the most recent critique."""
        return self._last_critique


# Global instance
_self_improvement_engine: SelfImprovementEngine | None = None


def get_self_improvement_engine() -> SelfImprovementEngine:
    global _self_improvement_engine
    if _self_improvement_engine is None:
        _self_improvement_engine = SelfImprovementEngine()
    return _self_improvement_engine
