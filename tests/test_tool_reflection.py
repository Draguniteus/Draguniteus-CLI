"""Tests for tool reflection — tracks per-tool stats, success rates, latency."""
import pytest
import sys
import time
sys.path.insert(0, 'src')

from draguniteus.tools.reflection import ToolReflection, get_tool_reflection


class TestToolReflection:
    """Test ToolReflection."""

    def setup_method(self):
        self.reflection = ToolReflection()
        self.reflection._stats.clear()  # fresh start

    def test_record_result_success(self):
        self.reflection.record_result("Write", True)
        stats = self.reflection.get_stats("Write")
        assert stats["call_count"] == 1
        assert stats["success_count"] == 1
        assert stats["failure_count"] == 0

    def test_record_result_failure(self):
        self.reflection.record_result("Bash", False, "Command failed")
        stats = self.reflection.get_stats("Bash")
        assert stats["call_count"] == 1
        assert stats["success_count"] == 0
        assert stats["failure_count"] == 1
        assert "Command failed" in stats["failure_reasons"]

    def test_multiple_results_accumulate(self):
        self.reflection.record_result("Write", True)
        self.reflection.record_result("Write", True)
        self.reflection.record_result("Write", False, "Permission denied")
        stats = self.reflection.get_stats("Write")
        assert stats["call_count"] == 3
        assert stats["success_count"] == 2
        assert stats["failure_count"] == 1

    def test_get_all_stats(self):
        self.reflection.record_result("Write", True)
        self.reflection.record_result("Bash", True)
        all_stats = self.reflection.get_all_stats()
        assert "Write" in all_stats
        assert "Bash" in all_stats

    def test_get_slowest_tools(self):
        # Record multiple tools with different call counts
        for _ in range(3):
            self.reflection.record_result("Bash", True)
        self.reflection.record_result("Read", True)

        slowest = self.reflection.get_slowest(2)
        assert len(slowest) <= 2
        # Read has 1 call, Bash has 3 — Bash should be slower

    def test_get_least_reliable(self):
        self.reflection.record_result("Write", True)
        self.reflection.record_result("Write", True)
        self.reflection.record_result("Write", False, "Permission denied")
        self.reflection.record_result("Edit", True)

        least_reliable = self.reflection.get_least_reliable(1)
        assert len(least_reliable) >= 1
        name, rate = least_reliable[0]
        assert name == "Write"
        assert rate == 2/3  # 66.7%

    def test_format_summary(self):
        self.reflection.record_result("Write", True)
        summary = self.reflection.format_summary()
        assert len(summary) > 0
        assert "Write" in summary

    def test_no_stats_for_unknown_tool(self):
        stats = self.reflection.get_stats("NonExistentTool")
        assert stats == {}

    def test_stats_have_expected_keys_after_record(self):
        # After record_result, stats should have call_count, success_count, etc.
        self.reflection.record_result("Read", True)
        stats = self.reflection.get_stats("Read")
        assert "call_count" in stats
        assert "success_count" in stats
        assert "failure_count" in stats


class TestGetToolReflection:
    """Test singleton accessor."""

    def test_returns_singleton(self):
        t1 = get_tool_reflection()
        t2 = get_tool_reflection()
        assert t1 is t2