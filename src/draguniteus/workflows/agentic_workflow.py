"""Agentic workflow engine: Plan → Execute → Verify → Iterate → Done.

State machine with checkpoint integration for resumable long-running tasks.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from draguniteus.theming import CYAN, DIM, GREEN, ORANGE, RED, RESET


class WorkflowPhase(Enum):
    PLANNING = "PLANNING"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    ITERATING = "ITERATING"
    DONE = "DONE"
    FAILED = "FAILED"


@dataclass
class WorkflowStep:
    """A single step in the workflow."""
    step_id: str
    description: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    result: Any = None
    verified: bool = False
    error: str = ""
    started_at: str = ""
    completed_at: str = ""


@dataclass
class WorkflowState:
    """Full workflow state — serializable to JSON."""
    workflow_id: str
    task_description: str
    phase: str = WorkflowPhase.PLANNING.value
    step_index: int = 0
    completed_steps: list[dict[str, Any]] = field(default_factory=list)
    verification_results: list[str] = field(default_factory=list)
    iteration_count: int = 0
    plan: list[str] = field(default_factory=list)
    messages: list[dict[str, Any]] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        self.updated_at = self.created_at

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, default=str)

    @classmethod
    def from_json(cls, data: str) -> "WorkflowState":
        d = json.loads(data)
        return cls(**d)


@dataclass
class WorkflowConfig:
    """Configuration for an agentic workflow."""
    max_iterations: int = 5
    checkpoint_every: int = 3
    auto_verify: bool = True
    verify_after_each_step: bool = False


class AgenticWorkflow:
    """Manages a Plan → Execute → Verify → Iterate → Done workflow loop.

    Integrates with CheckpointManager for crash recovery and with
    StreamingDisplay for phase badge display.
    """

    def __init__(
        self,
        workflow_id: str,
        task: str,
        config: WorkflowConfig | None = None,
    ):
        self.workflow_id = workflow_id
        self.task = task
        self.config = config or WorkflowConfig()
        self.state = WorkflowState(
            workflow_id=workflow_id,
            task_description=task,
        )
        self._phase_listeners: list[callable] = []

    @property
    def phase(self) -> WorkflowPhase:
        return WorkflowPhase(self.state.phase)

    def transition(self, new_phase: WorkflowPhase) -> None:
        """Transition to a new phase."""
        old = self.phase
        self.state.phase = new_phase.value
        self.state.updated_at = datetime.now().isoformat()
        for listener in self._phase_listeners:
            listener(old, new_phase)

    def add_step(self, description: str, tool_calls: list[dict[str, Any]] | None = None) -> str:
        """Add a planned step to the workflow."""
        step_id = f"step_{self.state.step_index:02d}"
        step = WorkflowStep(
            step_id=step_id,
            description=description,
            tool_calls=tool_calls or [],
            started_at=datetime.now().isoformat(),
        )
        self.state.plan.append(description)
        self.state.step_index += 1
        return step_id

    def complete_step(
        self,
        step_id: str,
        result: Any = None,
        verified: bool = False,
        error: str = "",
    ) -> None:
        """Mark a step as complete."""
        completed = {
            "step_id": step_id,
            "result": str(result)[:500] if result else "",
            "verified": verified,
            "error": error,
            "completed_at": datetime.now().isoformat(),
        }
        self.state.completed_steps.append(completed)

        if verified:
            self.state.verification_results.append(f"{step_id}: verified")
        elif error:
            self.state.verification_results.append(f"{step_id}: FAILED — {error}")

    def plan(self, plan_steps: list[str]) -> None:
        """Set the execution plan."""
        self.state.plan = list(plan_steps)
        self.transition(WorkflowPhase.PLANNING)

    def execute(self) -> None:
        """Begin execution phase."""
        self.transition(WorkflowPhase.EXECUTING)

    def verify(self, results: list[str]) -> bool:
        """Run verification phase. Returns True if all verifications passed."""
        self.transition(WorkflowPhase.VERIFYING)
        all_passed = all("FAILED" not in r for r in results)
        self.state.verification_results.extend(results)

        if all_passed:
            self.transition(WorkflowPhase.DONE)
        else:
            self.state.iteration_count += 1
            if self.state.iteration_count >= self.config.max_iterations:
                self.transition(WorkflowPhase.FAILED)
            else:
                self.transition(WorkflowPhase.ITERATING)

        return all_passed

    def iterate(self) -> None:
        """Transition to next iteration."""
        self.state.iteration_count += 1
        if self.state.iteration_count >= self.config.max_iterations:
            self.transition(WorkflowPhase.FAILED)
        else:
            self.transition(WorkflowPhase.ITERATING)

    def get_phase_badge(self) -> str:
        """Get a display badge for the current phase."""
        phase = self.phase
        badges = {
            WorkflowPhase.PLANNING: f"{CYAN}[PLAN]{RESET}",
            WorkflowPhase.EXECUTING: f"{ORANGE}[EXEC]{RESET}",
            WorkflowPhase.VERIFYING: f"{CYAN}[VERIFY]{RESET}",
            WorkflowPhase.ITERATING: f"{ORANGE}[ITERATE]{RESET}",
            WorkflowPhase.DONE: f"{GREEN}[DONE]{RESET}",
            WorkflowPhase.FAILED: f"{RED}[FAILED]{RESET}",
        }
        return badges.get(phase, "")

    def get_progress_summary(self) -> str:
        """Get a one-line progress summary."""
        phase = self.phase
        if phase == WorkflowPhase.DONE:
            return f"{self.state.step_index} steps completed successfully"
        elif phase == WorkflowPhase.FAILED:
            return f"Failed after {self.state.iteration_count} iterations"
        elif phase == WorkflowPhase.ITERATING:
            return f"Iteration {self.state.iteration_count}/{self.config.max_iterations} — fixing issues"
        elif phase == WorkflowPhase.VERIFYING:
            return f"Verifying {len(self.state.completed_steps)} completed steps"
        else:
            return f"{self.state.step_index} steps planned"

    def add_phase_listener(self, listener: callable) -> None:
        """Register a listener for phase transitions (e.g., StreamingDisplay)."""
        self._phase_listeners.append(listener)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self.state)

    def save_to_file(self, path: Path) -> None:
        """Save workflow state to a JSON file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.state.to_json(), encoding="utf-8")

    @classmethod
    def load_from_file(cls, path: Path, task: str = "") -> "AgenticWorkflow":
        """Load a workflow from a JSON file."""
        data = path.read_text(encoding="utf-8")
        state = WorkflowState.from_json(data)
        wf = cls(workflow_id=state.workflow_id, task=state.task_description or task)
        wf.state = state
        return wf
