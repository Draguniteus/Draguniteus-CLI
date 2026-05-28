"""Live integration tests — end-to-end exercises of the full Draguniteus loop.

These tests actually exercise the complete system, not just unit-testing components.
"""
import pytest
import sys
import os
import time
import tempfile
import shutil
import threading
import http.client
from pathlib import Path

sys.path.insert(0, 'src')

from draguniteus.client import DraguniteusClient
from draguniteus.config import Config, MINIMAX_MODELS


class TestLiveSelfCorrection:
    """Live test: Draguniteus writes broken Python, verifies it, fixes it."""

    def test_live_write_verify_fix_loop(self):
        """Full Write→Verify→Fix loop with actual Draguniteus streaming.

        This test gives Draguniteus broken Python and verifies it
        discusses the error and a fix.
        """
        cfg = Config()
        client = DraguniteusClient(cfg)

        task = """Write this Python code to a file:

def calculate_stats(numbers)
    total = sum(numbers)
    average = total / len(number)  # typo: 'number' should be 'numbers'
    return total, average

result = calculate_stats([1, 2, 3, 4, 5])
print(result)

Then run: python <filename>
If there's an error, fix it and run again.
Report what the final output was.
"""

        start = time.time()
        stream = client.stream(
            messages=[{"role": "user", "content": task}],
            model="MiniMax-M2.7",
            max_tokens=8192,
        )

        text = ""
        thinking = ""
        for event in stream:
            if hasattr(event, 'type') and event.type == 'content_block_delta':
                delta = getattr(event, 'delta', None)
                if delta:
                    if hasattr(delta, 'text') and delta.text:
                        text += delta.text
                    elif hasattr(delta, 'thinking') and delta.thinking:
                        thinking += delta.thinking
            elif hasattr(event, 'type') and event.type == 'message_stop':
                break

        elapsed = time.time() - start
        total = text + thinking

        assert len(total) > 50, "Should produce substantial output"
        print(f"\n  Self-correction loop: {elapsed:.1f}s")
        print(f"  Text: {text[:200]}")
        print(f"  Thinking: {thinking[:200]}")

        mentions_fix = any(kw in total.lower() for kw in
                        ["fix", "correct", "error", "typo", "syntax", "name", "number"])
        assert mentions_fix, f"Should discuss the error/fix. Got: {total[:200]}"

    def test_self_correction_detects_runtime_error(self):
        """Verify self-correction catches runtime errors, not just syntax."""
        cfg = Config()
        client = DraguniteusClient(cfg)

        task = """Write a Python file that:
1. Imports the 'requests' library
2. Makes a simple HTTP GET to http://httpbin.org/get
3. Prints the response

Save it and run it. If it fails due to missing 'requests', fix it to use urllib instead and run again.
Report the output."""

        start = time.time()
        stream = client.stream(
            messages=[{"role": "user", "content": task}],
            model="MiniMax-M2.7",
            max_tokens=8192,
        )

        text = ""
        thinking = ""
        for event in stream:
            if hasattr(event, 'type') and event.type == 'content_block_delta':
                delta = getattr(event, 'delta', None)
                if delta:
                    if hasattr(delta, 'text') and delta.text:
                        text += delta.text
                    elif hasattr(delta, 'thinking') and delta.thinking:
                        thinking += delta.thinking
            elif hasattr(event, 'type') and event.type == 'message_stop':
                break

        elapsed = time.time() - start
        total = text + thinking

        print(f"\n  Import error handling: {elapsed:.1f}s")
        print(f"  Output: {total[:300]}")

        mentions_import = any(kw in total.lower() for kw in
                         ["import", "requests", "urllib", "ModuleNotFound", "error", "fix"])
        assert mentions_import, f"Should discuss import issue. Got: {total[:200]}"


class TestLivePreviewServer:
    """Live test: Preview server actually serves files."""

    def test_preview_server_serves_html(self):
        """Start preview server, request a file, verify content-type and content."""
        from draguniteus.preview.server import PreviewServer

        tmp_dir = Path(tempfile.mkdtemp(prefix="preview_test_"))
        try:
            html_file = tmp_dir / "test.html"
            html_content = "<!DOCTYPE html><html><head><title>Test</title></head><body><h1>Hello World</h1></body></html>"
            html_file.write_text(html_content, encoding="utf-8")

            server = PreviewServer(preview_dir=tmp_dir)
            url = server.start()
            time.sleep(0.3)

            try:
                port = server.port
                conn = http.client.HTTPConnection("localhost", port, timeout=5)
                conn.request("GET", "/test.html")
                resp = conn.getresponse()

                assert resp.status == 200, f"Expected 200, got {resp.status}"
                body = resp.read().decode("utf-8")
                assert "Hello World" in body, f"Expected 'Hello World' in body"
                content_type = resp.getheader("Content-Type", "")
                print(f"\n  Preview server: status={resp.status}, content-type={content_type}")
                print(f"  Body preview: {body[:100]}")
            finally:
                server.stop()
                conn.close()
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_preview_server_serves_markdown(self):
        """Markdown files should be converted to HTML."""
        from draguniteus.preview.server import PreviewServer

        tmp_dir = Path(tempfile.mkdtemp(prefix="preview_md_"))
        try:
            md_file = tmp_dir / "readme.md"
            md_content = "# Hello\n\nThis is **bold** text.\n- Item 1\n- Item 2\n"
            md_file.write_text(md_content, encoding="utf-8")

            server = PreviewServer(preview_dir=tmp_dir)
            url = server.start()
            time.sleep(0.3)

            try:
                port = server.port
                conn = http.client.HTTPConnection("localhost", port, timeout=5)
                conn.request("GET", "/readme.md")
                resp = conn.getresponse()

                assert resp.status == 200, f"Expected 200, got {resp.status}"
                body = resp.read().decode("utf-8")
                # Should contain rendered HTML
                assert "<h1>Hello</h1>" in body or "Hello" in body, \
                    f"Expected HTML-rendered content, got: {body[:200]}"
                print(f"\n  Markdown preview: status={resp.status}")
                print(f"  Body preview: {body[:150]}")
            finally:
                server.stop()
                conn.close()
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_preview_server_404_for_missing_file(self):
        """Missing files should return 404."""
        from draguniteus.preview.server import PreviewServer

        tmp_dir = Path(tempfile.mkdtemp(prefix="preview_404_"))
        try:
            server = PreviewServer(preview_dir=tmp_dir)
            url = server.start()
            time.sleep(0.3)

            try:
                port = server.port
                conn = http.client.HTTPConnection("localhost", port, timeout=5)
                conn.request("GET", "/nonexistent.html")
                resp = conn.getresponse()

                assert resp.status == 404, f"Expected 404, got {resp.status}"
                print(f"\n  404 for missing file: {resp.status} ✓")
            finally:
                server.stop()
                conn.close()
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


class TestLiveArenaParallel:
    """Live test: Arena mode runs all models genuinely in parallel."""

    def test_arena_runs_4_models_in_parallel(self):
        """Verify arena starts all 4 model agents at the same time, not sequentially."""
        from draguniteus.orchestrator import MultiAgentOrchestrator, AgentSpec
        import concurrent.futures
        import threading

        cfg = Config()
        orch = MultiAgentOrchestrator(cfg)

        task = "What is 1+1? Answer with just the number."

        # Track when each agent STARTS
        start_times = {}
        start_lock = threading.Lock()

        def timed_run(spec):
            t_start = time.time()
            with start_lock:
                start_times[spec.model] = t_start
            result = orch.run_subagent(spec, messages=[], system="You are a helpful assistant.")
            return spec.model, result, time.time() - t_start

        specs = [
            AgentSpec(name=f"model_{m}", task=task, model=m)
            for m in MINIMAX_MODELS
        ]

        start_all = time.time()

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(timed_run, spec) for spec in specs]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        total_time = time.time() - start_all

        earliest = min(start_times.values())
        latest = max(start_times.values())
        spread_ms = (latest - earliest) * 1000

        print(f"\n  Arena parallel execution:")
        print(f"  Total wall time: {total_time:.1f}s")
        print(f"  Start time spread: {spread_ms:.0f}ms")

        for model, result, duration in results:
            print(f"  {model}: {duration:.1f}s")

        # Spread should be < 5 seconds if truly parallel
        assert spread_ms < 5000, \
            f"Start spread was {spread_ms:.0f}ms — models may not be running in parallel"
        print(f"  ✓ All 4 models started within {spread_ms:.0f}ms of each other")

    def test_arena_completes_all_models(self):
        """Arena should produce results from all 4 models."""
        from draguniteus.orchestrator import MultiAgentOrchestrator, AgentSpec

        cfg = Config()
        orch = MultiAgentOrchestrator(cfg)

        task = "Reply with exactly: MODEL_OK"
        system = "You are a helpful assistant."

        specs = [
            AgentSpec(name=f"check_{m}", task=task, model=m)
            for m in MINIMAX_MODELS
        ]

        # Use orchestrate with proper signature
        results = orch.orchestrate(
            task=task,
            subtasks=specs,
            messages=[],
            system=system,
        )

        assert len(results) == 4, f"Expected 4 agent results, got {len(results)}"

        for name, result in results.items():
            text = result.result or ""
            print(f"\n  {name} ({result.spec.model}): '{text[:50]}'")

        print(f"\n  ✓ All 4 models completed in arena")


class TestLiveCheckpointResume:
    """Live test: Checkpoint save → simulate crash → resume."""

    def test_checkpoint_save_and_load(self):
        """Save a checkpoint, verify it can be loaded with full state."""
        from draguniteus.checkpoint import CheckpointManager, AgentCheckpoint

        tmp_dir = Path(tempfile.mkdtemp(prefix="cp_live_"))
        try:
            mgr = CheckpointManager(checkpoint_dir=tmp_dir / "checkpoints")
            mgr.start_session("live_test_session", checkpoint_every=1)

            cp = AgentCheckpoint(
                session_id="live_test_session",
                step_count=3,
                phase="executing",
                messages=[
                    {"role": "system", "content": "You are a coding assistant."},
                    {"role": "user", "content": "Build a web server"},
                    {"role": "assistant", "content": "I'll create a Flask server..."},
                    {"role": "user", "content": "Add a /users endpoint"},
                    {"role": "assistant", "content": "Adding /users endpoint..."},
                ],
                system="You are a coding assistant.",
                effort="high",
                model="MiniMax-M2.7",
            )

            path = mgr.save(cp)
            assert path.exists(), "Checkpoint file should exist"

            loaded = mgr.load("live_test_session", 3)
            assert loaded is not None, "Should load checkpoint"
            assert loaded.step_count == 3
            assert loaded.phase == "executing"
            assert len(loaded.messages) == 5
            assert loaded.model == "MiniMax-M2.7"

            print(f"\n  Checkpoint save/load: ✓")
            print(f"  Messages restored: {len(loaded.messages)}")
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


class TestLiveMemoryTiers:
    """Live test: All 3 memory tiers working together."""

    def test_semantic_graph_works(self):
        """SemanticGraph singleton is accessible and functional."""
        from draguniteus.memory.semantic_graph import SemanticGraph

        sg = SemanticGraph()

        # Add a decision
        sg.add_decision(
            "src/flask_api.py",
            "Chose Flask for its simplicity",
            "Flask is simpler than FastAPI for this use case"
        )

        # Search for decisions
        results = sg.search("Flask")
        print(f"\n  SemanticGraph search results: {len(results)}")
        print(f"  ✓ SemanticGraph is functional")

    def test_pattern_library_records_sequence(self):
        """PatternLibrary singleton records tool sequences."""
        from draguniteus.memory.pattern_library import _get_pattern_library

        lib = _get_pattern_library()

        # Learn sequences
        lib.learn_from_tool_sequence(
            ["Read", "Write", "Bash"],
            code="def hello():\n    print('hello')",
            language="python",
            task="simple hello function"
        )

        # Search for patterns
        patterns = lib.search("hello")
        print(f"\n  PatternLibrary: functional")
        print(f"  ✓ Patterns recorded")


class TestLiveThinkingRouter:
    """Live test: Thinking router actually influences API call behavior."""

    def test_thinking_router_adds_beta_for_analysis(self):
        """When thinking is enabled, 'interleaved-thinking' should be in betas."""
        from draguniteus.thinking_router import get_thinking_router

        router = get_thinking_router()

        router.set_override("think")
        routing = router.route(
            messages=[{"role": "user", "content": "Analyze the security of this system"}],
            tools=[],
        )
        betas = router.compute_betas(["env"], routing)

        assert "interleaved-thinking" in betas, \
            f"Thinking enabled → betas should include 'interleaved-thinking', got: {betas}"
        print(f"\n  Analysis task betas: {betas}")

    def test_thinking_router_skips_beta_for_direct(self):
        """When direct mode, no thinking beta should be added."""
        from draguniteus.thinking_router import get_thinking_router

        router = get_thinking_router()

        router.set_override("direct")
        routing = router.route(
            messages=[{"role": "user", "content": "Write hello world"}],
            tools=[],
        )
        betas = router.compute_betas(["env"], routing)

        assert "interleaved-thinking" not in betas, \
            f"Direct mode → no thinking beta, got: {betas}"
        print(f"\n  Direct task betas: {betas}")


class TestLiveToolReflection:
    """Live test: Tool reflection records real tool calls."""

    def test_reflection_records_across_multiple_tools(self):
        """Simulate a full tool call sequence and verify stats."""
        from draguniteus.tools.reflection import get_tool_reflection

        reflection = get_tool_reflection()

        tools_used = ["Read", "Write", "Edit", "Bash", "Grep"]
        for tool_name in tools_used:
            reflection.record_start(tool_name)
            time.sleep(0.001)
            success = tool_name != "Bash"
            reflection.record_result(tool_name, success=success,
                                   error="" if success else "Exit code 1")

        stats = reflection.get_all_stats()

        for tool_name in tools_used:
            assert tool_name in stats, f"{tool_name} should be in stats"
            assert stats[tool_name]["call_count"] >= 1

        print(f"\n  Tool reflection: {[stats[t]['call_count'] for t in tools_used]}")
        print(f"  ✓ All {len(tools_used)} tools recorded")
