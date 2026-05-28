"""Tests for developer role adapter — injects structured context into each turn."""
import pytest
import sys
sys.path.insert(0, 'src')

from draguniteus.role_adapter import RoleAdapter, get_role_adapter


class TestRoleAdapter:
    """Test RoleAdapter."""

    def setup_method(self):
        self.ra = RoleAdapter()

    def test_enabled_by_default(self):
        assert self.ra.enabled is True

    def test_disabled_returns_empty(self):
        ra = RoleAdapter(enabled=False)
        result = ra.build_developer_message()
        assert result == ""

    def test_build_developer_message_empty_context(self):
        result = self.ra.build_developer_message()
        assert result == ""

    def test_build_developer_message_with_mode(self):
        self.ra.set_active_mode("debugging")
        result = self.ra.build_developer_message()
        assert "DEBUGGING" in result
        assert "Mode" in result

    def test_build_developer_message_with_tracked_files(self):
        self.ra.set_tracked_files(["src/main.py", "src/config.py"])
        result = self.ra.build_developer_message()
        assert "main.py" in result
        assert "config.py" in result

    def test_build_developer_message_with_tools_summary(self):
        result = self.ra.build_developer_message(
            tools_summary="Write, Edit, Bash, Grep, Glob"
        )
        assert "Write" in result
        assert "Bash" in result

    def test_build_developer_message_with_recent_results(self):
        result = self.ra.build_developer_message(
            recent_tool_results=["Write: ok", "Bash: pytest passed"]
        )
        assert "pytest" in result or "Bash" in result

    def test_build_developer_message_truncates_long_content(self):
        ra = RoleAdapter(max_tokens=100)
        ra.set_tracked_files([f"file_{i}.py" for i in range(20)])
        result = ra.build_developer_message()
        # Should be truncated to max_tokens (chars, not tokens)
        assert len(result) <= 500  # rough upper bound

    def test_set_project_constraints(self):
        self.ra.set_project_constraints("Use type hints. Max line length 100.")
        result = self.ra.build_developer_message()
        assert "type hints" in result or "constraints" in result

    def test_summarize_tool_results_all_success(self):
        tool_results = [
            {"name": "Write", "success": True},
            {"name": "Bash", "success": True},
        ]
        result = self.ra.summarize_tool_results(tool_results)
        assert "ok" in result
        assert "FAILED" not in result

    def test_summarize_tool_results_with_failure(self):
        tool_results = [
            {"name": "Write", "success": True},
            {"name": "Bash", "success": False, "error": "Permission denied"},
        ]
        result = self.ra.summarize_tool_results(tool_results)
        assert "FAILED" in result
        assert "Permission denied" in result

    def test_build_developer_message_for_turn(self):
        result = self.ra.build_developer_message_for_turn(
            messages=None,
            tools=[{"name": "Write"}, {"name": "Edit"}],
            tracked_files=["src/app.py"],
            mode="writing",
        )
        assert len(result) > 0
        assert "app.py" in result

    def test_build_developer_message_for_turn_no_context(self):
        result = self.ra.build_developer_message_for_turn()
        assert result == ""

    def test_truncate_preserves_short_content(self):
        text = "short text"
        result = RoleAdapter._truncate(text, 100)
        assert result == text

    def test_truncate_appends_ellipsis(self):
        text = "a" * 200
        result = RoleAdapter._truncate(text, 50)
        assert result.endswith("...")
        assert len(result) == 50


class TestGetRoleAdapter:
    """Test singleton accessor."""

    def test_returns_same_instance(self):
        r1 = get_role_adapter()
        r2 = get_role_adapter()
        assert r1 is r2