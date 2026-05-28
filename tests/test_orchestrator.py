"""Tests for orchestrator model routing."""
import pytest
import sys
sys.path.insert(0, 'src')

from draguniteus.orchestrator import MultiAgentOrchestrator, AgentSpec
from draguniteus.config import Config


class TestOrchestratorModelRouting:
    """Test orchestrator correctly routes different models."""

    def test_agent_spec_accepts_all_minimax_models(self):
        from draguniteus.config import MINIMAX_MODELS
        for m in MINIMAX_MODELS:
            spec = AgentSpec(name="test", task="test task", model=m)
            assert spec.model == m

    def test_get_client_for_model_via_raw(self):
        """Verify _get_client_for_model works without triggering read-only error."""
        cfg = Config()
        orch = MultiAgentOrchestrator(cfg)

        # This should NOT raise "property 'model' of 'Config' object has no setter"
        from draguniteus.config import MINIMAX_MODELS
        for m in MINIMAX_MODELS:
            client = orch._get_client_for_model(m)
            assert client is not None
            # The model should be set in the raw config
            assert client.config._raw.get("model") == m

    def test_agent_spec_default_model(self):
        spec = AgentSpec(name="test", task="test")
        assert spec.model == "MiniMax-M2.7"
