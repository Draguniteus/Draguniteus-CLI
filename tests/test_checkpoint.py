"""Tests for checkpoint system — save/load/resume lifecycle."""
import pytest
import sys
import uuid
import time
from pathlib import Path

sys.path.insert(0, 'src')

from draguniteus.checkpoint import (
    CheckpointManager, AgentCheckpoint, get_checkpoint_manager
)


class TestAgentCheckpoint:
    """Test AgentCheckpoint dataclass."""

    def test_creates_with_required_fields(self):
        cp = AgentCheckpoint(session_id="test-session", step_count=1)
        assert cp.session_id == "test-session"
        assert cp.step_count == 1
        assert cp.phase == "executing"
        assert len(cp.messages) == 0

    def test_auto_truncates_long_message_list(self):
        messages = [{"role": "system", "content": "sys"}] + [
            {"role": "user", "content": f"msg{i}"}
            for i in range(120)
        ]
        cp = AgentCheckpoint(
            session_id="test", step_count=1,
            messages=messages, max_message_turns=50
        )
        # Should keep system + last 50*2=100 non-system messages
        assert len(cp.messages) <= 101  # 1 system + 100 max

    def test_created_at_auto_set(self):
        cp = AgentCheckpoint(session_id="test", step_count=1)
        assert cp.created_at != ""


class TestCheckpointManager:
    """Test CheckpointManager lifecycle."""

    def setup_method(self):
        self.manager = get_checkpoint_manager()
        self.session_id = str(uuid.uuid4())
        self.manager.start_session(self.session_id, checkpoint_every=3)

    def teardown_method(self):
        self.manager.delete_session(self.session_id)

    def test_start_session_sets_current_session(self):
        mgr = CheckpointManager()
        sid = str(uuid.uuid4())
        mgr.start_session(sid)
        assert mgr.current_session == sid

    def test_tick_increments_step_count(self):
        assert self.manager.current_step == 0
        self.manager.tick()
        assert self.manager.current_step == 1
        self.manager.tick()
        assert self.manager.tick() == 3

    def test_should_checkpoint_every_n_turns(self):
        # checkpoint_every=3, so steps 3, 6, 9 should trigger
        assert self.manager.should_checkpoint() is False
        self.manager.tick()  # 1
        assert self.manager.should_checkpoint() is False
        self.manager.tick()  # 2
        assert self.manager.should_checkpoint() is False
        self.manager.tick()  # 3
        assert self.manager.should_checkpoint() is True
        self.manager.tick()  # 4
        assert self.manager.should_checkpoint() is False

    def test_save_and_load_checkpoint(self):
        cp = AgentCheckpoint(
            session_id=self.session_id,
            step_count=1,
            phase="planning",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "hello"},
            ],
            effort="high",
        )
        path = self.manager.save(cp)
        assert path.exists()

        loaded = self.manager.load(self.session_id, 1)
        assert loaded is not None
        assert loaded.step_count == 1
        assert loaded.phase == "planning"
        assert len(loaded.messages) == 2

    def test_load_latest_returns_most_recent(self):
        for i in [1, 2, 3]:
            self.manager.tick()
        cp = AgentCheckpoint(
            session_id=self.session_id,
            step_count=self.manager.current_step,
            phase="executing",
            messages=[{"role": "user", "content": "test"}],
        )
        self.manager.save(cp)

        latest = self.manager.load_latest(self.session_id)
        assert latest is not None
        assert latest.step_count == 3

    def test_list_checkpoints_returns_metadata(self):
        for i in [1, 2, 3]:
            self.manager.tick()
        cp = AgentCheckpoint(
            session_id=self.session_id,
            step_count=self.manager.current_step,
            messages=[],
        )
        self.manager.save(cp)

        checkpoints = self.manager.list_checkpoints(self.session_id)
        assert len(checkpoints) >= 1
        assert "step" in checkpoints[0]
        assert "phase" in checkpoints[0]

    def test_delete_session_removes_all_checkpoints(self):
        self.manager.tick()
        cp = AgentCheckpoint(
            session_id=self.session_id,
            step_count=1,
            messages=[],
        )
        self.manager.save(cp)

        remaining = self.manager.list_checkpoints(self.session_id)
        assert len(remaining) >= 1

        self.manager.delete_session(self.session_id)
        remaining = self.manager.list_checkpoints(self.session_id)
        assert len(remaining) == 0

    def test_checkpoint_prunes_old_files(self):
        mgr = CheckpointManager(checkpoint_every=1)
        sid = str(uuid.uuid4())
        mgr.start_session(sid, checkpoint_every=1)

        # Create 25 checkpoints
        for i in range(25):
            mgr.tick()
            cp = AgentCheckpoint(
                session_id=sid,
                step_count=mgr.current_step,
                messages=[],
            )
            mgr.save(cp)

        checkpoints = mgr.list_checkpoints(sid)
        # Should keep max 20
        assert len(checkpoints) <= 20
        mgr.delete_session(sid)

    def test_atomic_write_creates_temp_then_rename(self):
        cp = AgentCheckpoint(
            session_id=self.session_id,
            step_count=99,
            messages=[],
        )
        path = self.manager.save(cp)
        # File should exist at final path, not .tmp
        assert path.exists()
        assert ".tmp" not in str(path)


class TestGetCheckpointManager:
    """Test singleton accessor."""

    def test_returns_same_instance(self):
        m1 = get_checkpoint_manager()
        m2 = get_checkpoint_manager()
        assert m1 is m2