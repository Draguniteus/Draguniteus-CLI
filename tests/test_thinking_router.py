"""Tests for thinking router — hybrid thinking/direct classification."""
import pytest
import sys
sys.path.insert(0, 'src')

from draguniteus.thinking_router import (
    ThinkingRouter, get_thinking_router, REASONING_TASKS, DIRECT_TASKS
)


class TestThinkingRouter:
    """Test ThinkingRouter classification."""

    def setup_method(self):
        self.router = ThinkingRouter()

    # Reasoning tasks should trigger thinking mode
    @pytest.mark.parametrize("prompt", [
        "analyze this codebase",
        "debug why my API fails",
        "plan a migration",
        "explain why this happens",
        "investigate the memory leak",
        "assess the security risk",
        "design the architecture",
        "evaluate the tradeoffs",
        "review the code quality",
    ])
    def test_reasoning_tasks_trigger_thinking(self, prompt):
        messages = [{"role": "user", "content": prompt}]
        result = self.router.route(messages)
        assert result["thinking"] is True, f"'{prompt}' should trigger thinking"

    # Direct tasks should NOT trigger thinking
    @pytest.mark.parametrize("prompt", [
        "create a new file",
        "write unit tests",
        "add error handling",
        "fix the typo in README",
        "list all files",
        "what is the git status",
        "get the current time",
        "delete the temp files",
        "build the project",
    ])
    def test_direct_tasks_no_thinking(self, prompt):
        messages = [{"role": "user", "content": prompt}]
        result = self.router.route(messages)
        assert result["thinking"] is False, f"'{prompt}' should be direct"

    # Override: /think forces thinking
    def test_set_override_think(self):
        self.router.set_override("think")
        result = self.router.route([])
        assert result["mode"] == "forced_think"
        # Override should clear after use
        result2 = self.router.route([])
        assert result2["mode"] != "forced_think"

    # Override: /fast forces direct
    def test_set_override_direct(self):
        self.router.set_override("direct")
        result = self.router.route([])
        assert result["mode"] == "forced_direct"

    # Token budget heuristic
    def test_token_budget_triggers_direct(self):
        messages = [{"role": "user", "content": "hello"}]
        result = self.router.route(
            messages,
            context_tokens=180000,  # 90% of 200k
            max_context_tokens=200000
        )
        assert result["thinking"] is False
        assert result["mode"] == "token_budget"

    # Tool complexity heuristic
    def test_many_tools_triggers_thinking(self):
        messages = [{"role": "user", "content": "do something complex"}]
        tools = [{"name": f"tool{i}"} for i in range(5)]
        result = self.router.route(messages, tools=tools)
        assert result["thinking"] is True
        assert result["mode"] == "tool_complexity"

    def test_compute_betas_adds_thinking(self):
        base_betas = ["base-beta-1"]
        routing = {"thinking": True}
        result = self.router.compute_betas(base_betas, routing)
        assert "interleaved-thinking" in result

    def test_compute_betas_does_not_add_when_direct(self):
        base_betas = ["base-beta-1"]
        routing = {"thinking": False}
        result = self.router.compute_betas(base_betas, routing)
        assert result == base_betas

    def test_disabled_router_returns_direct(self):
        router = ThinkingRouter(enabled=False)
        result = router.route([{"role": "user", "content": "analyze"}])
        assert result["thinking"] is False
        # Mode should be "direct" when disabled (not explicitly "disabled")
        assert result["mode"] == "direct"

    def test_empty_messages_defaults_to_thinking(self):
        result = self.router.route([])
        assert result["thinking"] is True

    def test_get_thinking_router_returns_singleton(self):
        r1 = get_thinking_router()
        r2 = get_thinking_router()
        assert r1 is r2


class TestTaskKeywordSets:
    """Test that keyword sets are properly defined."""

    def test_reasoning_tasks_has_expected_keywords(self):
        expected = {"analyze", "debug", "plan", "explain why", "investigate"}
        for kw in expected:
            assert kw in REASONING_TASKS, f"'{kw}' should be in REASONING_TASKS"

    def test_direct_tasks_has_expected_keywords(self):
        expected = {"write", "create", "add", "fix", "list", "what is"}
        for kw in expected:
            assert kw in DIRECT_TASKS, f"'{kw}' should be in DIRECT_TASKS"

    def test_fix_keyword_catches_fix_something(self):
        """'fix' should match 'fix the bug' but not 'analyze fix'."""
        router = ThinkingRouter()
        # 'fix' alone should be direct
        messages = [{"role": "user", "content": "fix the bug"}]
        result = router.route(messages)
        assert result["thinking"] is False