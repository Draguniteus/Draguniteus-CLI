"""Skill evaluation framework for quantitative benchmarking."""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from draguniteus.config import DEFAULT_CONFIG_DIR


@dataclass
class EvalCase:
    """A test case for skill evaluation."""
    id: str
    prompt: str
    expected_output: str | None = None
    assertions: list[dict] | None = None
    created_at: str = ""

    def __init__(self, prompt: str, expected_output: str | None = None, assertions: list[dict] | None = None):
        self.id = str(uuid.uuid4())[:8]
        self.prompt = prompt
        self.expected_output = expected_output
        self.assertions = assertions or []
        self.created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


@dataclass
class EvalResult:
    """Result of a single eval run."""
    eval_id: str
    skill_name: str
    prompt: str
    passed: bool
    output: str
    duration_ms: float
    tokens_used: int | None = None
    timestamp: str = ""
    error: str | None = None

    def __init__(self, eval_id: str, skill_name: str, prompt: str, passed: bool, output: str, duration_ms: float, tokens_used: int | None = None, error: str | None = None):
        self.eval_id = eval_id
        self.skill_name = skill_name
        self.prompt = prompt
        self.passed = passed
        self.output = output
        self.duration_ms = duration_ms
        self.tokens_used = tokens_used
        self.timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self.error = error

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(init=False)
class BenchmarkReport:
    """Full benchmark report for a skill."""
    skill_name: str
    total_evals: int
    passed: int
    failed: int
    pass_rate: float
    avg_duration_ms: float
    total_tokens: int | None = None
    results: list[dict]
    timestamp: str = ""

    def __init__(self, skill_name: str, results: list[EvalResult]):
        self.skill_name = skill_name
        self.results = [r.to_dict() for r in results]
        self.total_evals = len(results)
        self.passed = sum(1 for r in results if r.passed)
        self.failed = self.total_evals - self.passed
        self.pass_rate = (self.passed / self.total_evals * 100) if self.total_evals > 0 else 0
        self.avg_duration_ms = sum(r.duration_ms for r in results) / self.total_evals if self.total_evals > 0 else 0
        self.total_tokens = sum(r.tokens_used or 0 for r in results)
        self.timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill_name": self.skill_name,
            "total_evals": self.total_evals,
            "passed": self.passed,
            "failed": self.failed,
            "pass_rate": f"{self.pass_rate:.1f}%",
            "avg_duration_ms": f"{self.avg_duration_ms:.0f}ms",
            "total_tokens": self.total_tokens,
            "timestamp": self.timestamp,
        }

    def summary(self) -> str:
        return (f"Skill: {self.skill_name}\n"
                f"Pass: {self.passed}/{self.total_evals} ({self.pass_rate:.1f}%)\n"
                f"Avg time: {self.avg_duration_ms:.0f}ms\n"
                f"Tokens: {self.total_tokens or 'N/A'}")


class SkillEvaluator:
    """Framework for running quantitative skill evaluations."""

    def __init__(self, skill_name: str):
        self.skill_name = skill_name
        self.evals_dir = DEFAULT_CONFIG_DIR / "evals" / skill_name
        self.evals_dir.mkdir(parents=True, exist_ok=True)
        self._evals: list[EvalCase] = []
        self._load_evals()

    def _load_evals(self) -> None:
        """Load evals from evals/evals.json if it exists."""
        evals_file = self.evals_dir / "evals.json"
        if evals_file.exists():
            try:
                data = json.loads(evals_file.read_text(encoding="utf-8"))
                for e in data.get("evals", []):
                    case = EvalCase.__new__(EvalCase)
                    case.id = e.get("id", str(uuid.uuid4())[:8])
                    case.prompt = e.get("prompt", "")
                    case.expected_output = e.get("expected_output")
                    case.assertions = e.get("assertions", [])
                    case.created_at = e.get("created_at", "")
                    self._evals.append(case)
            except Exception:
                pass

    def add_eval(self, prompt: str, expected_output: str | None = None, assertions: list[dict] | None = None) -> EvalCase:
        """Add an eval case to the skill's test suite."""
        case = EvalCase(prompt, expected_output, assertions)
        self._evals.append(case)
        self._save_evals()
        return case

    def _save_evals(self) -> None:
        """Save evals to evals/evals.json."""
        evals_file = self.evals_dir / "evals.json"
        data = {
            "skill_name": self.skill_name,
            "evals": [
                {"id": e.id, "prompt": e.prompt, "expected_output": e.expected_output,
                 "assertions": e.assertions or [], "created_at": e.created_at}
                for e in self._evals
            ]
        }
        evals_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _evaluate_assertions(self, output: str, assertions: list[dict]) -> bool:
        """Check if output satisfies all assertions.

        Assertion format:
          {"type": "contains", "value": "some text"}
          {"type": "regex", "pattern": "some pattern"}
          {"type": "json_eq", "path": "$.key", "value": "expected"}
        """
        import re
        import json

        for assertion in assertions:
            atype = assertion.get("type", "")
            if atype == "contains":
                if assertion.get("value", "") not in output:
                    return False
            elif atype == "regex":
                pattern = assertion.get("pattern", "")
                if not re.search(pattern, output):
                    return False
            elif atype == "json_eq":
                path = assertion.get("path", "")
                expected = assertion.get("value")
                try:
                    data = json.loads(output)
                    key = path.replace("$.", "")
                    if data.get(key) != expected:
                        return False
                except Exception:
                    return False
        return True

    def run_evals(self, skill_content: str) -> BenchmarkReport:
        """Run all eval cases against a skill and return benchmark report.

        Executes each eval case's prompt through the skill via execute_skill(),
        then evaluates the output against the case's assertions.
        """
        from draguniteus.tools.skills import Skill, execute_skill

        results = []
        for eval_case in self._evals:
            start = time.time()
            try:
                # Build a Skill object from content
                skill = Skill(
                    name=self.skill_name,
                    description="",
                    content=skill_content,
                    metadata={}
                )

                # Execute the skill with the eval prompt
                exec_result = execute_skill(skill, {"query": eval_case.prompt})
                output = exec_result["output"]

                # Evaluate assertions if present
                if eval_case.assertions:
                    passed = self._evaluate_assertions(output, eval_case.assertions)
                else:
                    passed = exec_result["success"]
                error = None
            except Exception as e:
                output = ""
                passed = False
                error = str(e)
            duration = (time.time() - start) * 1000

            result = EvalResult(
                eval_id=eval_case.id,
                skill_name=self.skill_name,
                prompt=eval_case.prompt,
                passed=passed,
                output=output[:500] if output else "",
                duration_ms=duration,
                error=error
            )
            results.append(result)

        report = BenchmarkReport(self.skill_name, results)
        self._save_report(report)
        return report

    def _save_report(self, report: BenchmarkReport) -> None:
        """Save benchmark report to evals/benchmark.json."""
        report_file = self.evals_dir / "benchmark.json"
        report_file.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")

    def get_report(self) -> BenchmarkReport | None:
        """Get the latest benchmark report if it exists."""
        report_file = self.evals_dir / "benchmark.json"
        if report_file.exists():
            try:
                data = json.loads(report_file.read_text(encoding="utf-8"))
                # Reconstruct from results
                results = []
                for r_data in data.get("results", []):
                    results.append(EvalResult(**r_data))
                return BenchmarkReport(data["skill_name"], results)
            except Exception:
                return None
        return None

    def list_evals(self) -> list[EvalCase]:
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


class SkillDescriptionOptimizer:
    """Optimize skill descriptions for better triggering accuracy."""

    def __init__(self, skill_name: str):
        self.skill_name = skill_name

    def analyze_triggers(self, description: str) -> dict[str, Any]:
        """Analyze a description and suggest improvements for triggering.

        Looks for:
        - Specific trigger phrases (vs vague descriptions)
        - Clear "when to use" language
        - Pushy/active language that encourages use
        - Coverage of edge cases
        """
        suggestions = []
        warnings = []

        words = description.lower().split()
        has_when = "when" in words or "when the user" in description.lower()
        has_ask = "ask" in words or "asks" in words

        # Check for vague trigger patterns
        vague_patterns = ["sometimes", "maybe", "if needed", "as appropriate"]
        for vp in vague_patterns:
            if vp in description.lower():
                warnings.append(f"Consider removing vague phrase: '{vp}'")

        # Check for passive language
        passive_phrases = ["you might want to", "could consider", "it may be useful to"]
        for pp in passive_phrases:
            if pp in description.lower():
                suggestions.append(f"Replace passive phrase with active: '{pp}'")

        # Check description length
        if len(description) < 100:
            suggestions.append("Description is short. Consider adding more trigger contexts.")

        # Check for trigger variety
        trigger_indicators = ["when the user", "if the user", "ask to", "asks to", "mentions", "wants to", "needs to"]
        found = sum(1 for t in trigger_indicators if t in description.lower())
        if found < 2:
            suggestions.append("Add more trigger contexts (when/if user...)")

        return {
            "warnings": warnings,
            "suggestions": suggestions,
            "word_count": len(words),
            "has_when_clause": has_when,
        }

    def generate_improved_description(self, current: str, intent: str, use_cases: list[str]) -> str:
        """Generate an improved description with better triggering."""
        use_cases_text = "\n".join(f"- {uc}" for uc in use_cases)
        return f"""This skill should be used when the user asks to "{intent}" or describes wanting to {intent}.

Use cases:
{use_cases_text}

Make sure to use this skill whenever the user mentions {intent.split()[0] if intent else 'this topic'}, even if they don't explicitly ask for it by name."""


# Global evaluator registry
_evaluators: dict[str, SkillEvaluator] = {}


def get_skill_evaluator(skill_name: str) -> SkillEvaluator:
    """Get or create a skill evaluator."""
    if skill_name not in _evaluators:
        _evaluators[skill_name] = SkillEvaluator(skill_name)
    return _evaluators[skill_name]