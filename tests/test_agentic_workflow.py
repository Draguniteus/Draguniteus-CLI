"""Tests for agentic workflow state machine — Plan→Execute→Verify→Iterate→Done."""
import pytest
import sys
import uuid
sys.path.insert(0, 'src')

from draguniteus.workflows.agentic_workflow import (
    AgenticWorkflow, WorkflowPhase, WorkflowState, WorkflowConfig
)


class TestWorkflowPhase:
    """Test WorkflowPhase enum."""

    def test_has_all_phases(self):
        assert hasattr(WorkflowPhase, 'PLANNING')
        assert hasattr(WorkflowPhase, 'EXECUTING')
        assert hasattr(WorkflowPhase, 'VERIFYING')
        assert hasattr(WorkflowPhase, 'ITERATING')
        assert hasattr(WorkflowPhase, 'DONE')
        assert hasattr(WorkflowPhase, 'FAILED')

    def test_phase_order(self):
        # Verify phase values are distinct and expected (uppercase enum style)
        assert WorkflowPhase.PLANNING.value == "PLANNING"
        assert WorkflowPhase.EXECUTING.value == "EXECUTING"
        assert WorkflowPhase.VERIFYING.value == "VERIFYING"
        assert WorkflowPhase.ITERATING.value == "ITERATING"
        assert WorkflowPhase.DONE.value == "DONE"
        assert WorkflowPhase.FAILED.value == "FAILED"


class TestWorkflowState:
    """Test WorkflowState dataclass."""

    def test_creates_with_defaults(self):
        state = WorkflowState(
            workflow_id="test-123",
            task_description="test task"
        )
        assert state.workflow_id == "test-123"
        assert state.phase == WorkflowPhase.PLANNING.value
        assert state.completed_steps == []
        assert state.iteration_count == 0

    def test_to_json_and_back(self):
        state = WorkflowState(
            workflow_id="test-456",
            task_description="build something"
        )
        json_str = state.to_json()
        restored = WorkflowState.from_json(json_str)
        assert restored.workflow_id == "test-456"
        assert restored.task_description == "build something"


class TestAgenticWorkflow:
    """Test AgenticWorkflow state machine."""

    def setup_method(self):
        self.wf = AgenticWorkflow(
            workflow_id=str(uuid.uuid4()),
            task="test workflow"
        )

    def test_initial_phase_is_planning(self):
        assert self.wf.state.phase == WorkflowPhase.PLANNING.value

    def test_transition_to_executing(self):
        self.wf.transition(WorkflowPhase.EXECUTING)
        assert self.wf.state.phase == WorkflowPhase.EXECUTING.value

    def test_transition_sequence_planning_to_done(self):
        phases = [
            WorkflowPhase.PLANNING,
            WorkflowPhase.EXECUTING,
            WorkflowPhase.VERIFYING,
            WorkflowPhase.ITERATING,
            WorkflowPhase.DONE,
        ]
        for phase in phases:
            self.wf.transition(phase)
            assert self.wf.state.phase == phase.value

    def test_transition_to_failed(self):
        self.wf.transition(WorkflowPhase.FAILED)
        assert self.wf.state.phase == WorkflowPhase.FAILED.value

    def test_add_step(self):
        step_id = self.wf.add_step("Write config file")
        assert step_id is not None
        assert len(self.wf.state.plan) == 1

    def test_add_multiple_steps(self):
        self.wf.add_step("Step 1")
        self.wf.add_step("Step 2")
        self.wf.add_step("Step 3")
        assert len(self.wf.state.plan) == 3

    def test_complete_step(self):
        step_id = self.wf.add_step("Test step")
        self.wf.complete_step(step_id, verified=True)
        assert len(self.wf.state.completed_steps) == 1
        assert self.wf.state.completed_steps[0]["verified"] is True

    def test_complete_step_with_error(self):
        step_id = self.wf.add_step("Fail step")
        self.wf.complete_step(step_id, verified=False, error="Something broke")
        assert len(self.wf.state.completed_steps) == 1
        assert self.wf.state.completed_steps[0]["error"] == "Something broke"

    def test_get_phase_badge(self):
        self.wf.transition(WorkflowPhase.PLANNING)
        badge = self.wf.get_phase_badge()
        assert "PLAN" in badge or "[PLAN]" in badge

        self.wf.transition(WorkflowPhase.EXECUTING)
        badge = self.wf.get_phase_badge()
        assert "EXEC" in badge or "[EXEC]" in badge

    def test_get_progress_summary(self):
        self.wf.add_step("Step 1")
        self.wf.add_step("Step 2")
        self.wf.transition(WorkflowPhase.EXECUTING)
        summary = self.wf.get_progress_summary()
        assert isinstance(summary, str)
        assert len(summary) > 0

    def test_reset_step_index_on_new_workflow(self):
        wf1 = AgenticWorkflow(workflow_id=str(uuid.uuid4()), task="task1")
        wf1.add_step("step")
        assert wf1.state.step_index == 1

        wf2 = AgenticWorkflow(workflow_id=str(uuid.uuid4()), task="task2")
        assert wf2.state.step_index == 0

    def test_workflow_state_json_round_trip(self):
        wf = AgenticWorkflow(
            workflow_id="test-roundtrip",
            task="roundtrip test"
        )
        wf.add_step("Step 1")
        wf.transition(WorkflowPhase.EXECUTING)

        json_str = wf.state.to_json()
        restored = WorkflowState.from_json(json_str)
        assert restored.workflow_id == "test-roundtrip"
        assert len(restored.plan) == 1