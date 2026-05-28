"""Tests for nested tool executor — retry logic and error classification."""
import pytest
import sys
sys.path.insert(0, 'src')

from draguniteus.tools.nested_tool_executor import (
    NestedToolExecutor, ToolCallNode, RetryPolicy
)


class TestToolCallNode:
    """Test ToolCallNode."""

    def test_creates_with_pending_status(self):
        node = ToolCallNode(name="Write", args={"file_path": "test.py"})
        assert node.status == "pending"
        assert node.depth == 0
        assert node.attempts == 0

    def test_creates_with_specified_depth(self):
        node = ToolCallNode(name="mcp__github__create_issue", args={}, depth=2)
        assert node.depth == 2

    def test_result_and_error_set_on_failure(self):
        node = ToolCallNode(name="Bash", args={"command": "ls"})
        node.status = "failed"
        node.error = "Permission denied"
        assert node.status == "failed"
        assert node.error == "Permission denied"


class TestRetryPolicy:
    """Test RetryPolicy."""

    def test_default_values(self):
        policy = RetryPolicy()
        assert policy.max_attempts == 3
        assert policy.base_delay == 1.0
        assert policy.max_delay == 10.0

    def test_exponential_backoff_multiplicative(self):
        policy = RetryPolicy()
        assert policy.multiplicative is True


class TestNestedToolExecutor:
    """Test NestedToolExecutor."""

    def setup_method(self):
        self.executor = NestedToolExecutor(max_depth=5)

    def test_max_depth_set(self):
        assert self.executor.max_depth == 5

    def test_is_transient_timeout(self):
        assert self.executor._is_transient_error("TimeoutError: timed out") is True
        assert self.executor._is_transient_error("timeout connecting to server") is True

    def test_is_transient_connection_refused(self):
        assert self.executor._is_transient_error("Connection refused") is True

    def test_is_transient_rate_limit(self):
        assert self.executor._is_transient_error("rate limit exceeded") is True
        assert self.executor._is_transient_error("429 Too Many Requests") is True

    def test_is_transient_503(self):
        assert self.executor._is_transient_error("503 Service Unavailable") is True

    def test_is_transient_502(self):
        assert self.executor._is_transient_error("502 Bad Gateway") is True

    def test_is_permanent_file_not_found(self):
        assert self.executor._is_transient_error("File not found") is False

    def test_is_permanent_permission_denied(self):
        assert self.executor._is_transient_error("Permission denied") is False

    def test_is_permanent_invalid_argument(self):
        assert self.executor._is_transient_error("Invalid argument") is False

    def test_is_permanent_400(self):
        assert self.executor._is_transient_error("400 Bad Request") is False

    def test_is_permanent_401(self):
        assert self.executor._is_transient_error("401 Unauthorized") is False

    def test_is_permanent_404(self):
        assert self.executor._is_transient_error("404 Not Found") is False

    def test_exponential_backoff_delay_increases(self):
        delays = [self.executor._compute_delay(i) for i in [1, 2, 3]]
        assert delays[1] > delays[0]
        assert delays[2] > delays[1]

    def test_exponential_backoff_respects_max_delay(self):
        # Even with many retries, delay should stay under max_delay
        for attempt in range(1, 10):
            delay = self.executor._compute_delay(attempt)
            assert delay <= 10.0 + 0.1  # small tolerance for jitter