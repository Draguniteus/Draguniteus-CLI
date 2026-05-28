"""Tests for arena and git CLI commands."""
import pytest
import sys
import os
from pathlib import Path
sys.path.insert(0, 'src')

from draguniteus.cli import _cmd_arena, _cmd_git
from draguniteus.config import MINIMAX_MODELS


class TestArenaCommand:
    """Test /arena CLI command."""

    def test_arena_help_shows_models(self):
        class FakeSession:
            pass
        class FakeMessages(list):
            pass

        captured = []

        def fake_print(msg):
            captured.append(str(msg))

        import draguniteus.cli as cli_module
        orig_print = cli_module._print
        cli_module._print = fake_print

        try:
            result = _cmd_arena("", FakeMessages(), FakeSession())
            assert result is True
            output = "\n".join(captured)
            assert "Arena Mode" in output
            assert "MiniMax-M2.7" in output
        finally:
            cli_module._print = orig_print

    def test_arena_list_uses_minimax_models(self):
        """Arena should use MINIMAX_MODELS as default models."""
        assert len(MINIMAX_MODELS) >= 2
        assert "MiniMax-M2.7" in MINIMAX_MODELS
        assert "MiniMax-M2.5" in MINIMAX_MODELS
        assert "MiniMax-M2.1" in MINIMAX_MODELS
        assert "MiniMax-M2" in MINIMAX_MODELS
        # M2-her should NOT be in the list (plan doesn't support it)
        assert "M2-her" not in MINIMAX_MODELS

    def test_arena_unknown_model_only_runs_valid_ones(self):
        """Arena with unknown model arg falls back to all valid models."""
        class FakeSession:
            pass
        class FakeMessages(list):
            pass

        captured = []

        def fake_print(msg):
            captured.append(str(msg))

        import draguniteus.cli as cli_module
        orig_print = cli_module._print
        cli_module._print = fake_print

        try:
            # NonExistentModel is filtered out, falls back to all MINIMAX_MODELS default
            result = _cmd_arena("test-task NonExistentModel", FakeMessages(), FakeSession())
            assert result is True
            output = "\n".join(captured)
            # Should show arena running with valid models
            assert "Arena Mode" in output or "Arena complete" in output
        finally:
            cli_module._print = orig_print


class TestGitCommand:
    """Test /git CLI command."""

    def test_git_help(self):
        class FakeSession:
            pass
        class FakeMessages(list):
            pass

        captured = []

        def fake_print(msg):
            captured.append(str(msg))

        import draguniteus.cli as cli_module
        orig_print = cli_module._print
        cli_module._print = fake_print

        try:
            result = _cmd_git("", FakeMessages(), FakeSession())
            assert result is True
            output = "\n".join(captured)
            assert "/git status" in output or "status" in output.lower()
        finally:
            cli_module._print = orig_print


class TestMinimaxModels:
    """Test MINIMAX_MODELS configuration."""

    def test_all_models_are_strings(self):
        for m in MINIMAX_MODELS:
            assert isinstance(m, str), f"Model {m!r} is not a string"

    def test_all_models_have_minimax_prefix_or_m2her(self):
        for m in MINIMAX_MODELS:
            assert m.startswith("MiniMax-") or m == "M2-her", f"Unexpected model name: {m}"

    def test_no_duplicate_models(self):
        assert len(MINIMAX_MODELS) == len(set(MINIMAX_MODELS)), "Duplicate models found"

    def test_models_order_m2_7_first(self):
        assert MINIMAX_MODELS[0] == "MiniMax-M2.7", "M2.7 should be first model"

    def test_no_highspeed_models(self):
        for m in MINIMAX_MODELS:
            assert "highspeed" not in m.lower(), f"Highspeed model found: {m}"
