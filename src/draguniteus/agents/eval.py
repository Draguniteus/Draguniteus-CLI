"""Agent evaluation framework for quantitative benchmarking and triggering analysis."""
from __future__ import annotations

import json
import time
import uuid
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

from draguniteus.agents.loader import AgentLoader, get_agent_loader
from draguniteus.config import DEFAULT_CONFIG_DIR


@dataclass
class AgentEvalCase:
    """A test case for agent evaluation."""
    id: str
    query: str
    expected_agent: str | None = None
    description_patterns: list[str] = field(default_factory=list)
    created_at: str = ""

    def __init__(self, query: str, expected_agent: str | None = None, description_patterns: list[str] | None = None):
        self.id = str(uuid.uuid4())[:8]
        self.query = query
        self.expected_agent = expected_agent
        self.description_patterns = description_patterns or []
        self.created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


@dataclass
class AgentEvalResult:
    """Result of a single agent eval run."""
    eval_id: str
    agent_name: str
    query: str
    triggered: bool
    output: str
    duration_ms: float
    match_score: float = 0.0
    timestamp: str = ""
    error: str | None = None

    def __init__(self, eval_id: str, agent_name: str, query: str, triggered: bool, output: str = "", duration_ms: float = 0.0, match_score: float = 0.0, error: str | None = None):
        self.eval_id = eval_id
        self.agent_name = agent_name
        self.query = query
        self.triggered = triggered
        self.output = output
        self.duration_ms = duration_ms
        self.match_score = match_score
        self.timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self.error = error

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AgentBenchmarkReport:
    """Full benchmark report for agent triggering."""
    agent_name: str
    total_evals: int
    triggered: int
    missed: int
    trigger_rate: float
    avg_match_score: float
    avg_duration_ms: float
    results: list[dict]
    timestamp: str = ""

    def __init__(self, agent_name: str, results: list[AgentEvalResult]):
        self.agent_name = agent_name
        self.results = [r.to_dict() for r in results]
        self.total_evals = len(results)
        self.triggered = sum(1 for r in results if r.triggered)
        self.missed = self.total_evals - self.triggered
        self.trigger_rate = (self.triggered / self.total_evals * 100) if self.total_evals > 0 else 0
        self.avg_match_score = sum(r.match_score for r in results) / self.total_evals if self.total_evals > 0 else 0
        self.avg_duration_ms = sum(r.duration_ms for r in results) / self.total_evals if self.total_evals > 0 else 0
        self.timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_name": self.agent_name,
            "total_evals": self.total_evals,
            "triggered": self.triggered,
            "missed": self.missed,
            "trigger_rate": f"{self.trigger_rate:.1f}%",
            "avg_match_score": f"{self.avg_match_score:.2f}",
            "avg_duration_ms": f"{self.avg_duration_ms:.0f}ms",
            "timestamp": self.timestamp,
        }

    def summary(self) -> str:
        return (f"Agent: {self.agent_name}\n"
                f"Trigger: {self.triggered}/{self.total_evals} ({self.trigger_rate:.1f}%)\n"
                f"Avg match score: {self.avg_match_score:.2f}\n"
                f"Avg time: {self.avg_duration_ms:.0f}ms")


class AgentEvaluator:
    """Framework for running quantitative agent evaluations."""

    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        self.evals_dir = DEFAULT_CONFIG_DIR / "agent_evals" / agent_name
        self.evals_dir.mkdir(parents=True, exist_ok=True)
        self._evals: list[AgentEvalCase] = []
        self._load_evals()

    def _load_evals(self) -> None:
        """Load evals from agent_evals/evals.json if it exists."""
        evals_file = self.evals_dir / "evals.json"
        if evals_file.exists():
            try:
                data = json.loads(evals_file.read_text(encoding="utf-8"))
                for e in data.get("evals", []):
                    case = AgentEvalCase.__new__(AgentEvalCase)
                    case.id = e.get("id", str(uuid.uuid4())[:8])
                    case.query = e.get("query", "")
                    case.expected_agent = e.get("expected_agent")
                    case.description_patterns = e.get("description_patterns", [])
                    case.created_at = e.get("created_at", "")
                    self._evals.append(case)
            except Exception:
                pass

    def add_eval(self, query: str, expected_agent: str | None = None, description_patterns: list[str] | None = None) -> AgentEvalCase:
        """Add an eval case to the agent's test suite."""
        case = AgentEvalCase(query, expected_agent, description_patterns)
        self._evals.append(case)
        self._save_evals()
        return case

    def _save_evals(self) -> None:
        """Save evals to agent_evals/evals.json."""
        evals_file = self.evals_dir / "evals.json"
        data = {
            "agent_name": self.agent_name,
            "evals": [
                {"id": e.id, "query": e.query, "expected_agent": e.expected_agent,
                 "description_patterns": e.description_patterns, "created_at": e.created_at}
                for e in self._evals
            ]
        }
        evals_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def run_evals(self, agent_definition: str) -> AgentBenchmarkReport:
        """Run all eval cases against an agent definition and return benchmark report.

        Evaluates:
        - Does the agent description trigger for the given query
        - Does the match score meet threshold
        """
        loader = get_agent_loader()
        agent = loader.get_agent(self.agent_name)

        results = []
        for eval_case in self._evals:
            start = time.time()
            try:
                if agent:
                    # Check if query matches agent description
                    match_score = self._calculate_match_score(agent, eval_case.query)
                    triggered = match_score >= 0.3  # Threshold
                    output = f"[Eval {eval_case.id}] Agent {self.agent_name} match_score={match_score:.2f}"
                else:
                    match_score = 0.0
                    triggered = False
                    output = f"[Eval {eval_case.id}] Agent {self.agent_name} not found"
                error = None
            except Exception as e:
                match_score = 0.0
                triggered = False
                output = ""
                error = str(e)
            duration = (time.time() - start) * 1000

            result = AgentEvalResult(
                eval_id=eval_case.id,
                agent_name=self.agent_name,
                query=eval_case.query,
                triggered=triggered,
                output=output,
                duration_ms=duration,
                match_score=match_score,
                error=error
            )
            results.append(result)

        report = AgentBenchmarkReport(self.agent_name, results)
        self._save_report(report)
        return report

    def _calculate_match_score(self, agent, query: str) -> float:
        """Calculate how well a query matches an agent definition.

        Uses:
        - Keyword overlap between query and description
        - Example block pattern matching
        - Trigger phrase presence
        """
        score = 0.0
        query_lower = query.lower()
        desc_lower = agent.description.lower()

        # Direct keyword match
        query_words = set(query_lower.split())
        desc_words = set(desc_lower.split())
        overlap = query_words & desc_words
        if query_words:
            score += len(overlap) / len(query_words) * 0.4

        # Example block matching - check if query fits example patterns
        if "<example>" in agent.body.lower():
            # Extract example patterns
            example_sections = re.findall(r"<example>(.*?)</example>", agent.body, re.DOTALL | re.IGNORECASE)
            for section in example_sections:
                if "user:" in section.lower() and query_lower in section.lower():
                    score += 0.3
                    break

        # Trigger phrase detection
        trigger_phrases = ["when the user", "if the user", "asks to", "wants to", "mentions"]
        for phrase in trigger_phrases:
            if phrase in desc_lower and phrase in query_lower:
                score += 0.2
                break

        # "use this agent" phrase match
        if "use this agent" in desc_lower or "use this skill" in desc_lower:
            if query_lower in desc_lower:
                score += 0.1

        return min(score, 1.0)

    def _save_report(self, report: AgentBenchmarkReport) -> None:
        """Save benchmark report to agent_evals/benchmark.json."""
        report_file = self.evals_dir / "benchmark.json"
        report_file.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")

    def get_report(self) -> AgentBenchmarkReport | None:
        """Get the latest benchmark report if it exists."""
        report_file = self.evals_dir / "benchmark.json"
        if report_file.exists():
            try:
                data = json.loads(report_file.read_text(encoding="utf-8"))
                return AgentBenchmarkReport(data["agent_name"], [])
            except Exception:
                return None
        return None

    def list_evals(self) -> list[AgentEvalCase]:
        """List all eval cases."""
        return list(self._evals)

    def delete_eval(self, eval_id: str) -> bool:
        """Delete an eval case by ID."""
        before = len(self._evals)
        self._evals = [e for e in self._evals if e.id != eval_id]
        if len(self._evals) != before:
            self._save_evals()
            return True
        return False


class AgentDescriptionOptimizer:
    """Optimize agent descriptions for better triggering accuracy."""

    def __init__(self, agent_name: str):
        self.agent_name = agent_name

    def analyze_triggers(self, description: str) -> dict[str, Any]:
        """Analyze a description and suggest improvements for triggering.

        Looks for:
        - Specific trigger phrases (vs vague descriptions)
        - Clear "when to use" language
        - Example blocks with varied patterns
        - Pushy/active language that encourages use
        - Coverage of edge cases
        """
        suggestions = []
        warnings = []

        desc_lower = description.lower()
        words = desc_lower.split()

        # Check for vague trigger patterns
        vague_patterns = ["sometimes", "maybe", "if needed", "as appropriate", "might want to"]
        for vp in vague_patterns:
            if vp in desc_lower:
                warnings.append(f"Consider removing vague phrase: '{vp}'")

        # Check for passive language
        passive_phrases = ["you might want to", "could consider", "it may be useful to", "you may want to"]
        for pp in passive_phrases:
            if pp in desc_lower:
                suggestions.append(f"Replace passive phrase with active: '{pp}'")

        # Check description length
        if len(description) < 100:
            suggestions.append("Description is short. Add more trigger contexts and examples.")

        # Check for trigger variety
        trigger_indicators = ["when the user", "if the user", "ask to", "asks to", "mentions", "wants to", "needs to", "use this agent"]
        found = sum(1 for t in trigger_indicators if t in desc_lower)
        if found < 2:
            suggestions.append("Add more trigger contexts (when/if user...)")

        # Check for example blocks
        example_count = len(re.findall(r"<example>", description, re.IGNORECASE))
        if example_count == 0:
            suggestions.append("Add <example> blocks to show triggering scenarios")
        elif example_count < 2:
            suggestions.append("Consider adding more example blocks for coverage")

        return {
            "warnings": warnings,
            "suggestions": suggestions,
            "word_count": len(words),
            "example_count": example_count,
            "trigger_phrase_count": found,
        }

    def generate_improved_description(self, current: str, agent_name: str, trigger_queries: list[str]) -> str:
        """Generate an improved description with better triggering.

        Args:
            current: Current description text
            agent_name: Name of the agent
            trigger_queries: List of queries that should trigger this agent
        """
        examples_text = "\n".join(
            f"""<example>
Context: User wants to {q}
user: "{q}"
assistant: "I'll help you {q}..."
<commentary>
The {agent_name} agent should trigger for this query.
</commentary>
</example>"""
            for q in trigger_queries
        )

        return f"""Use this agent when the user asks to "{agent_name}" or describes wanting to {agent_name}.

Examples:
{examples_text}

Make sure to use this agent whenever the user mentions {agent_name}, even if they don't explicitly ask for it by name."""


# Global evaluator registry
_agent_evaluators: dict[str, AgentEvaluator] = {}


def get_agent_evaluator(agent_name: str) -> AgentEvaluator:
    """Get or create an agent evaluator."""
    if agent_name not in _agent_evaluators:
        _agent_evaluators[agent_name] = AgentEvaluator(agent_name)
    return _agent_evaluators[agent_name]
