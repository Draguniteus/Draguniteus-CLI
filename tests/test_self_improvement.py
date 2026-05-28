"""Tests for self-improvement engine — critique and pattern learning."""
import pytest
import sys
sys.path.insert(0, 'src')

from draguniteus.self_improvement import SelfImprovementEngine, get_self_improvement_engine


class TestSelfImprovementEngine:
    """Test SelfImprovementEngine."""

    def setup_method(self):
        self.engine = get_self_improvement_engine()

    def test_critique_with_successful_tools(self):
        task = "Create a Flask web server"
        tool_results = [
            {"name": "Write", "success": True, "output": "Created app.py"},
            {"name": "Bash", "success": True, "output": "Flask installed"},
        ]
        messages = [{"role": "user", "content": task}]
        critique = self.engine.critique(task, tool_results, messages)
        assert isinstance(critique, str)
        assert len(critique) > 0
        assert "success" in critique.lower() or "ok" in critique.lower()

    def test_critique_with_failed_tool(self):
        task = "Install dependencies"
        tool_results = [
            {"name": "Bash", "success": False, "error": "pip install failed"},
        ]
        messages = []
        critique = self.engine.critique(task, tool_results, messages, outcome="failed")
        assert isinstance(critique, str)
        assert len(critique) > 0

    def test_critique_empty_when_disabled(self):
        engine = SelfImprovementEngine(enabled=False)
        critique = engine.critique("test", [], [])
        assert critique == ""

    def test_critique_includes_tool_names(self):
        task = "Build project"
        tool_results = [
            {"name": "Write", "success": True},
            {"name": "Bash", "success": True},
        ]
        messages = []
        critique = self.engine.critique(task, tool_results, messages)
        assert "Write" in critique or "Bash" in critique

    def test_critique_includes_success_rate(self):
        task = "Test task"
        tool_results = [
            {"name": "Write", "success": True},
            {"name": "Bash", "success": True},
        ]
        messages = []
        critique = self.engine.critique(task, tool_results, messages)
        # Should mention 2/2 or 100%
        assert "2/2" in critique or "100%" in critique or "ok" in critique.lower()

    def test_singleton(self):
        e1 = get_self_improvement_engine()
        e2 = get_self_improvement_engine()
        assert e1 is e2


class TestCritiqueOutput:
    """Test critique output content and format."""

    def setup_method(self):
        self.engine = get_self_improvement_engine()

    def test_critique_format_includes_task(self):
        task = "Create REST API"
        tool_results = [{"name": "Write", "success": True}]
        messages = []
        critique = self.engine.critique(task, tool_results, messages)
        assert "Create REST API" in critique

    def test_critique_contains_recommendations(self):
        task = "Build something"
        tool_results = [
            {"name": "Write", "success": True},
            {"name": "Edit", "success": False, "error": "File not found"},
        ]
        messages = []
        critique = self.engine.critique(task, tool_results, messages, outcome="partial")
        # Should have recommendations or analysis
        assert len(critique) > 50

    def test_critique_with_empty_messages(self):
        task = "Simple task"
        tool_results = [{"name": "Bash", "success": True}]
        critique = self.engine.critique(task, tool_results, messages=[])
        assert isinstance(critique, str)
        assert len(critique) > 0