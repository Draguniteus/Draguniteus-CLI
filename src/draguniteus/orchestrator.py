"""Multi-agent orchestration: parallel subagent execution with model specialization."""
from __future__ import annotations

import time
import signal
from typing import Any
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeoutError
import threading

from draguniteus.config import Config


class AgentSpec:
    """Specification for a subagent task."""

    def __init__(self, name: str, task: str, model: str = "MiniMax-M2.7",
                 tools: list[str] | None = None, max_turns: int = 10,
                 timeout_seconds: float = 120.0):
        self.name = name
        self.task = task
        self.model = model
        self.tools = tools
        self.max_turns = max_turns
        self.timeout_seconds = timeout_seconds


class OrchestratorResult:
    def __init__(self, spec: AgentSpec, result: str, tool_results: list[dict],
                 duration_ms: float, error: str | None = None,
                 timed_out: bool = False):
        self.spec = spec
        self.result = result
        self.tool_results = tool_results
        self.duration_ms = duration_ms
        self.error = error
        self.timed_out = timed_out


class MultiAgentOrchestrator:
    """Coordinates multiple subagents to work on subtasks in parallel.

    Usage:
        orchestrator = MultiAgentOrchestrator(config)
        result = orchestrator.orchestrate(task_description, subtasks)
    """

    def __init__(self, config):
        self.config = config
        self._agent_pool: dict[str, Any] = {}
        self._lock = threading.Lock()
        self._cancelled = threading.Event()
        self._interrupted = threading.Event()

    def _get_client_for_model(self, model: str):
        """Get or create a client bound to a specific model."""
        with self._lock:
            if model not in self._agent_pool:
                from draguniteus.client import DraguniteusClient
                client = DraguniteusClient(self.config)
                # Use _raw["model"] directly since Config.model is a read-only property
                self._agent_pool[model] = DraguniteusClient.__new__(DraguniteusClient)
                self._agent_pool[model]._sync = client._sync
                self._agent_pool[model]._async = client._async
                self._agent_pool[model].config = Config.__new__(Config)
                self._agent_pool[model].config._raw = {**client.config._raw, "model": model}
            return self._agent_pool[model]

    def cancel(self) -> None:
        """Signal all subagents to stop."""
        self._cancelled.set()

    def cleanup(self) -> None:
        """Clean up all agent pool clients. Call after orchestration session ends."""
        with self._lock:
            self._agent_pool.clear()
            self._cancelled.clear()
            self._interrupted.clear()

    def run_subagent(self, spec: AgentSpec, messages: list[dict], system: str,
                     progress_callback=None) -> OrchestratorResult:
        """Run a single subagent task with timeout and error handling.

        Args:
            spec: Agent specification
            messages: Conversation history
            system: System prompt
            progress_callback: Optional callback(agent_name, partial_text, thinking, tool_count, done)
        """
        if self._cancelled.is_set():
            return OrchestratorResult(spec, "", [], 0, "Cancelled before start", False)

        client = self._get_client_for_model(spec.model)
        start = time.time()

        sub_system = (
            f"{system}\n\n"
            f"You are the [{spec.name}] agent. Your task: {spec.task}\n\n"
            f"Focus exclusively on your assigned task. "
            f"Max turns: {spec.max_turns}."
        )

        tool_results: list[dict] = []
        try:
            from draguniteus.agent import StreamHandler
            stream = client.stream(
                messages=[{"role": "user", "content": spec.task}],
                tools=self._get_tools(spec.tools),
                system=sub_system,
            )
            handler = StreamHandler(None, full_drama=False)
            for event in stream:
                if self._cancelled.is_set():
                    # Drain remaining events then exit
                    while True:
                        try:
                            next(stream, None)
                        except (StopIteration, GeneratorExit, Exception):
                            break
                    return OrchestratorResult(
                        spec, handler.get_text(), handler.get_tool_calls(),
                        (time.time() - start) * 1000, "Cancelled during execution", False
                    )
                handler.handle_event(event)
                # Emit partial results via callback
                if progress_callback:
                    partial_text = handler.get_text()
                    thinking = handler.get_thinking()
                    tool_calls = handler.get_tool_calls()
                    progress_callback(
                        spec.name,
                        partial_text,
                        thinking,
                        len(tool_calls),
                        False,
                    )
                # Collect tool calls as they come
                if handler.get_tool_calls():
                    tool_results = handler.get_tool_calls()

            result_text = handler.get_text()
            thinking = handler.get_thinking()
            if thinking:
                result_text = f"[Thinking: {thinking[:200]}...]\n\n{result_text}"

            if progress_callback:
                progress_callback(spec.name, result_text, thinking, len(tool_results), True)

            return OrchestratorResult(
                spec, result_text, tool_results, (time.time() - start) * 1000
            )
        except Exception as e:
            if progress_callback:
                progress_callback(spec.name, "", "", 0, True)
            return OrchestratorResult(
                spec, "", tool_results, (time.time() - start) * 1000, str(e)
            )

    def _get_tools(self, tool_names: list[str] | None):
        """Get tool schemas for the specified tools, or all tools if None."""
        from draguniteus.client import DraguniteusClient
        all_tools = DraguniteusClient.get_tool_schemas()
        if tool_names is None:
            return all_tools
        return [t for t in all_tools if t.get("name") in tool_names]

    def orchestrate(self, task: str, subtasks: list[AgentSpec],
                    messages: list[dict], system: str,
                    timeout_per_agent: float | None = None,
                    progress_callback=None,
                    overall_timeout: float | None = 300.0) -> dict[str, OrchestratorResult]:
        """Run multiple subtasks in parallel with timeout per agent.

        Args:
            task: The overall task description
            subtasks: List of AgentSpec, each describing a subtask
            messages: Conversation history to provide context
            system: System prompt
            timeout_per_agent: Max seconds per agent (default from spec.timeout_seconds)
            progress_callback: Optional callback(agent_name, partial_text, thinking, tool_count, done)
                               Called from subagent threads whenever there's partial output.
            overall_timeout: Max seconds for the entire orchestration (default 300s).

        Returns:
            Dict mapping agent name -> OrchestratorResult
        """
        self._cancelled.clear()
        results: dict[str, OrchestratorResult] = {}

        with ThreadPoolExecutor(max_workers=len(subtasks)) as executor:
            futures = {}
            for spec in subtasks:
                timeout = timeout_per_agent or spec.timeout_seconds
                future = executor.submit(
                    self.run_subagent, spec, messages, system, progress_callback
                )
                futures[future] = spec

            overall_deadline = time.time() + overall_timeout if overall_timeout else None

            for future in as_completed(futures, timeout=overall_timeout):
                # Check if we've exceeded the overall timeout
                if overall_deadline and time.time() > overall_deadline:
                    # Cancel remaining futures
                    self.cancel()
                    for f in futures:
                        if not f.done():
                            f.cancel()
                    break

                spec = futures[future]
                timeout = timeout_per_agent or spec.timeout_seconds
                try:
                    result = future.result(timeout=max(1, timeout - (time.time() - (overall_deadline - overall_timeout) if overall_deadline else timeout)))
                except FuturesTimeoutError:
                    result = OrchestratorResult(
                        spec, "", [], timeout * 1000,
                        f"Timed out after {timeout}s", timed_out=True
                    )
                except Exception as e:
                    result = OrchestratorResult(spec, "", [], 0, str(e))
                results[spec.name] = result

        return results

    def aggregate(self, results: dict[str, OrchestratorResult], task: str) -> str:
        """Combine multiple agent results into a coherent response."""
        lines = [f"## Multi-Agent Results: {task}\n"]
        lines.append(f"_{len(results)} agent(s) completed_\n")

        succeeded = sum(1 for r in results.values() if not r.error)
        timed_out = sum(1 for r in results.values() if r.timed_out)
        failed = sum(1 for r in results.values() if r.error and not r.timed_out)

        if timed_out or failed:
            lines.append(f"⚠️  {succeeded} succeeded, {timed_out} timed out, {failed} failed\n")
        else:
            lines.append(f"✅ {succeeded}/{len(results)} agents completed successfully\n")

        for name, result in results.items():
            lines.append(f"\n### [{name}] — {result.spec.model}")
            lines.append(f"_{result.duration_ms / 1000:.1f}s_")

            if result.timed_out:
                lines.append(f"⏱️  Timed out after {result.duration_ms / 1000:.1f}s")
            elif result.error:
                lines.append(f"❌ Error: `{result.error}`")
            else:
                # Show result with tool use summary
                if result.tool_results:
                    tool_counts: dict[str, int] = {}
                    for tr in result.tool_results:
                        tool = tr.get("tool", "?")
                        tool_counts[tool] = tool_counts.get(tool, 0) + 1
                    tools_str = ", ".join(f"{v}× {k}" for k, v in tool_counts.items())
                    lines.append(f"_Used: {tools_str}_")
                lines.append(f"\n{result.result}")

        return "\n".join(lines)