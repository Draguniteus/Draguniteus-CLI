"""Tests for session branching (git-like sessions)."""
import pytest
import time
from pathlib import Path
from draguniteus.session import Session, SessionStore


class TestSessionBranching:
    def test_session_has_branch_fields(self):
        """Session dataclass has branch_from, branch_name, parent_id fields."""
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        s = Session(
            id="sess_test123",
            created_at=now,
            last_updated=now,
            model="MiniMax-M2.7",
            working_dir="/tmp",
            transcript_path="/tmp/test.jsonl",
            branch_from="sess_parent",
            branch_name="experiment-1",
            parent_id="sess_parent",
        )
        assert s.branch_from == "sess_parent"
        assert s.branch_name == "experiment-1"
        assert s.parent_id == "sess_parent"

    def test_session_branching_creates_new_session(self, tmp_path):
        """branch_session creates a new session with parent link."""
        # Create a temporary config dir
        import os
        old_home = os.environ.get("HOME")
        os.environ["HOME"] = str(tmp_path)

        try:
            store = SessionStore()
            parent = store.create("MiniMax-M2.7")

            # Branch it
            branch = store.branch_session(parent.id, "try-auth")
            assert branch is not None
            assert branch.branch_from == parent.id
            assert branch.branch_name == "try-auth"
            assert branch.parent_id == parent.id
            assert branch.id != parent.id

            # Parent still exists
            assert store.get(parent.id) is not None

        finally:
            if old_home:
                os.environ["HOME"] = old_home

    def test_get_branch_children(self, tmp_path):
        """get_branch_children returns sessions branched from a given session."""
        import os
        old_home = os.environ.get("HOME")
        os.environ["HOME"] = str(tmp_path)

        try:
            store = SessionStore()
            parent = store.create("MiniMax-M2.7")
            branch1 = store.branch_session(parent.id, "exp-1")
            branch2 = store.branch_session(parent.id, "exp-2")

            children = store.get_branch_children(parent.id)
            child_ids = [c.id for c in children]
            assert branch1.id in child_ids
            assert branch2.id in child_ids

        finally:
            if old_home:
                os.environ["HOME"] = old_home

    def test_get_ancestors(self, tmp_path):
        """get_ancestors returns the full ancestor chain."""
        import os
        old_home = os.environ.get("HOME")
        os.environ["HOME"] = str(tmp_path)

        try:
            store = SessionStore()
            root = store.create("MiniMax-M2.7")
            child = store.branch_session(root.id, "child-branch")
            grandchild = store.branch_session(child.id, "grandchild-branch")

            ancestors = store.get_ancestors(grandchild.id)
            ancestor_ids = [a.id for a in ancestors]
            assert root.id in ancestor_ids
            assert child.id in ancestor_ids
            assert len(ancestor_ids) == 2

        finally:
            if old_home:
                os.environ["HOME"] = old_home

    def test_branch_preserves_parent_transcript(self, tmp_path):
        """Branching copies parent transcript so history is preserved."""
        import os
        old_home = os.environ.get("HOME")
        os.environ["HOME"] = str(tmp_path)

        try:
            store = SessionStore()
            parent = store.create("MiniMax-M2.7")
            store.append_event(parent, {"role": "user", "content": "hello"})

            branch = store.branch_session(parent.id, "experiment")
            branch_events = store.load_transcript(branch)
            assert len(branch_events) == 1
            assert branch_events[0]["content"] == "hello"

        finally:
            if old_home:
                os.environ["HOME"] = old_home

    def test_branch_from_nonexistent_returns_none(self, tmp_path):
        """branch_session returns None for nonexistent session."""
        import os
        old_home = os.environ.get("HOME")
        os.environ["HOME"] = str(tmp_path)

        try:
            store = SessionStore()
            result = store.branch_session("nonexistent", "orphan")
            assert result is None

        finally:
            if old_home:
                os.environ["HOME"] = old_home