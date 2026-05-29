"""Main agent loop: handles streaming, tool dispatch, and response rendering."""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Iterator

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.text import Text

from draguniteus import client, config, theming
from draguniteus.client import DraguniteusClient
from draguniteus.config import Config
from draguniteus.tools import TOOL_MAP

# Output size limits to prevent memory exhaustion
MAX_TEXT_PARTS_SIZE = 10 * 1024 * 1024  # 10 MB cap on accumulated text
MAX_TOOL_RESULT_SIZE = 500 * 1024  # 500 KB cap on tool results sent to model

# Use the themed console from theming.py instead of creating a new one
_console = theming.console

# File tracking for rules injection
_TRACKED_FILES: list[str] = []


def track_file(file_path: str) -> None:
    """Track a file that was touched, for rules injection."""
    if file_path and file_path not in _TRACKED_FILES:
        _TRACKED_FILES.append(file_path)


def get_tracked_files() -> list[str]:
    return list(_TRACKED_FILES)


def clear_tracked_files() -> None:
    global _TRACKED_FILES
    _TRACKED_FILES.clear()


def _track_tool_files(name: str, parsed: dict[str, Any]) -> None:
    """Track files from tool arguments for rules injection."""
    if name in ("Read", "Write", "Edit", "Glob", "Grep"):
        fp = parsed.get("file_path") or parsed.get("path")
        if fp:
            track_file(str(fp))
    elif name == "Bash":
        # Track current working directory for bash
        import os
        track_file(os.getcwd())


# Lazy import to avoid circular imports
def _get_hook_runner():
    from draguniteus.hook_runner import get_hook_runner
    return get_hook_runner()


class StreamHandler:
    """Accumulates streaming events and renders progressively via Rich."""

    def __init__(self, console: Console, full_drama: bool = True, on_tool_call: callable = None, on_tool_start: callable = None, on_tool_use_start: callable = None):
        self.console = console
        self.full_drama = full_drama
        self._text_parts: list[str] = []
        self._thinking_parts: list[str] = []
        self._tool_calls: list[dict] = []
        self._current_tool: dict | None = None
        self._input_tokens: int = 0
        self._output_tokens: int = 0
        self._text_size_bytes: int = 0  # Track accumulated size
        self._truncated: bool = False  # Set to True if output was truncated
        self._on_tool_call = on_tool_call  # Callback when tool call completes (content_block_stop)
        self._on_tool_start = on_tool_start  # Callback when tool starts (content_block_start)
        self._on_tool_use_start = on_tool_use_start  # Callback when tool_use block starts with partial args
        self._current_block_type: str | None = None  # 'thinking', 'text', 'tool_use'
        self._thinking_active: bool = False  # True when receiving thinking_delta events
        self._thinking_block_ended: bool = False  # True when thinking content block has ended

    def _append_text(self, text: str) -> None:
        """Append text with size limit enforcement."""
        text_bytes = len(text.encode("utf-8"))
        if self._text_size_bytes + text_bytes > MAX_TEXT_PARTS_SIZE:
            remaining = MAX_TEXT_PARTS_SIZE - self._text_size_bytes
            if remaining > 0:
                self._text_parts.append(text[:remaining])
                self._text_size_bytes += remaining
            self._truncated = True
            self._text_parts.append("[...output truncated due to size...]")
        else:
            self._text_parts.append(text)
            self._text_size_bytes += text_bytes

    def handle_event(self, event: Any) -> str | None:
        """Process a streaming event. Returns any tool call to execute."""
        event_type = getattr(event, "type", None)
        if event_type is None:
            return None

        # Content block start
        if event_type == "content_block_start":
            block = getattr(event, "content_block", None)
            if block:
                btype = getattr(block, "type", None)
                if btype == "tool_use":
                    tool_name = getattr(block, "name", "Unknown")
                    self._current_tool = {"name": tool_name, "args": ""}
                    self._tool_calls.append(self._current_tool)
                    # Immediately notify via callback when tool starts
                    if self._on_tool_start and tool_name:
                        self._on_tool_start(tool_name)
                    # Separate callback for tool_use block start (fires before args accumulate)
                    if self._on_tool_use_start and tool_name:
                        self._on_tool_use_start(tool_name, "")
                elif btype == "thinking":
                    self._thinking_parts = []
                    self._current_block_type = "thinking"
                    self._thinking_active = True
                    self._thinking_block_ended = False
                elif btype == "text":
                    self._current_block_type = "text"
                elif btype == "tool_use":
                    self._current_block_type = "tool_use"

        # Content block delta
        elif event_type == "content_block_delta":
            delta = getattr(event, "delta", None)
            if delta is None:
                return None

            dtype = getattr(delta, "type", None)
            if dtype == "text_delta":
                text = getattr(delta, "text", "")
                self._append_text(text)
                return None
            elif dtype == "thinking_delta":
                thinking = getattr(delta, "thinking", "")
                self._thinking_parts.append(thinking)
                return None
            elif dtype == "signature_delta":
                # MiniMax uses signature_delta for thinking metadata/signature
                # This is a cryptographic artifact - do NOT add to thinking content
                return None
            elif dtype == "input_json_delta":
                arg_text = getattr(delta, "partial_json", "")
                if self._current_tool is not None:
                    self._current_tool["args"] += arg_text
                    # Notify of progressive args accumulation (for tool bullet update)
                    if self._on_tool_use_start:
                        self._on_tool_use_start(self._current_tool["name"], self._current_tool["args"])
                return None

        # Content block stop
        elif event_type == "content_block_stop":
            # If the thinking block just ended, mark it
            if self._current_block_type == "thinking":
                self._thinking_active = False
                self._thinking_block_ended = True
            self._current_block_type = None
            if self._current_tool:
                tc = self._current_tool
                self._current_tool = None
                # Immediately notify via callback if registered
                if self._on_tool_call and tc.get("name"):
                    self._on_tool_call(tc)
                return tc

        # Message delta (final tokens)
        elif event_type == "message_delta":
            delta = getattr(event, "delta", None)
            if delta:
                text = getattr(delta, "text", "")
                if text:
                    self._append_text(text)

        # Message stop — extract usage
        elif event_type == "message_stop":
            usage = getattr(event, "usage", None)
            if usage:
                self._input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
                self._output_tokens = int(getattr(usage, "output_tokens", 0) or 0)

        return None

    def handle_message(self, message: Any) -> list[dict[str, Any]]:
        """Process a completed non-streaming message, extract tool calls."""
        tool_results = []
        for block in message.content:
            btype = getattr(block, "type", None)
            if btype == "tool_use":
                name = getattr(block, "name", "")
                input_json = getattr(block, "input", {})
                tool_results.append({"name": name, "input": input_json})
        return tool_results

    def get_text(self) -> str:
        return "".join(self._text_parts)

    def get_thinking(self) -> str:
        return "".join(self._thinking_parts)

    def get_usage(self) -> tuple[int, int]:
        """Return (input_tokens, output_tokens)."""
        return self._input_tokens, self._output_tokens

    def is_thinking_active(self) -> bool:
        """True while thinking content is being received."""
        return self._thinking_active

    def is_thinking_done(self) -> bool:
        """True once the thinking content block has ended."""
        return self._thinking_block_ended

    def get_estimated_output_tokens(self) -> int:
        """Estimate output tokens from accumulated text + thinking parts.

        Uses ~4 chars per token as an estimate. This provides a real-time
        token count during streaming since the API only provides token
        counts at message_stop.
        """
        text_chars = sum(len(p.encode('utf-8')) for p in self._text_parts)
        thinking_chars = sum(len(p.encode('utf-8')) for p in self._thinking_parts)
        total_chars = text_chars + thinking_chars
        return max(1, total_chars // 4)

    def get_tool_calls(self) -> list[dict]:
        return self._tool_calls


def stream_one_turn(
    client: DraguniteusClient,
    messages: list[dict],
    system: str | None,
    config: Config,
    full_drama: bool = True,
    on_tool_call: callable = None,
    on_tool_start: callable = None,
    on_tool_use_start: callable = None,
) -> Iterator[tuple[str, str, list[dict] | None, bool, bool, bool, int]]:
    """Stream a single agent turn, yielding progressive results for Rich.Live display.

    Yields tuples of (text, thinking, pending_tool_calls_or_None, is_final, thinking_active, thinking_done, estimated_tokens).
    - text: partial response text accumulated so far
    - thinking: partial thinking text accumulated so far
    - pending_tool_calls: list of completed tool calls when a tool is fully parsed (None otherwise)
    - is_final: True only when the streaming phase is done (all events drained)
    - thinking_active: True while thinking content is being received
    - thinking_done: True once the thinking content block has ended
    - estimated_tokens: estimated output token count (real-time estimate during streaming)

    After is_final=True with tool_calls populated, the caller must execute tools
    and call back with results. This function does NOT execute tools — it only
    streams and yields. This allows the caller to display progressively during streaming.
    """
    tools = client.get_tool_schemas()
    console = _console
    handler = StreamHandler(console, full_drama, on_tool_call=on_tool_call, on_tool_start=on_tool_start, on_tool_use_start=on_tool_use_start)

    # --- Thinking Router: decide thinking vs direct ---
    router = None
    routing = {"thinking": False, "mode": "default", "reason": ""}
    if getattr(config, "thinking_router_enabled", True):
        try:
            from draguniteus.thinking_router import get_thinking_router
            router = get_thinking_router()
            # Estimate context tokens from messages
            import tiktoken
            try:
                enc = tiktoken.get_encoding("cl100k_base")
                context_tokens = sum(len(enc.encode(str(m.get("content", "")))) for m in messages[-5:])
            except Exception:
                context_tokens = sum(len(str(m.get("content", ""))) // 4 for m in messages[-5:])
            routing = router.route(messages, system or "", tools, context_tokens=context_tokens, max_context_tokens=getattr(config, "model_context_window", 204800))
        except Exception:
            pass

    effort_settings = config.get_effort_settings()
    betas = effort_settings.get("betas", [])
    if routing.get("thinking") and router:
        betas = router.compute_betas(betas, routing)
    elif not routing.get("thinking"):
        # Ensure thinking is NOT in betas for direct answers
        betas = [b for b in betas if "thinking" not in b.lower()]

    # --- Developer Role: inject developer context into system prompt if enabled ---
    if getattr(config, "developer_role_enabled", True):
        try:
            from draguniteus.role_adapter import get_role_adapter
            adapter = get_role_adapter()
            adapter.set_tracked_files(get_tracked_files() or [])
            developer_content = adapter.build_developer_message_for_turn(
                messages=messages,
                tools=tools,
                tracked_files=get_tracked_files(),
            )
            if developer_content:
                system = (system or "") + "\n\n[Developer Context]\n" + developer_content
        except Exception:
            pass

    api_messages = list(messages)
    stream = client.stream(
        messages=api_messages,
        tools=tools,
        system=system,
        betas=betas,
    )

    pending_tool_calls: list[dict] = []

    for event in stream:
        result = handler.handle_event(event)
        if result:
            pending_tool_calls.append(result)

        text = handler.get_text()
        thinking = handler.get_thinking()
        # Update handler's token usage so caller can access it
        in_tok, out_tok = handler.get_usage()
        handler._input_tokens = in_tok
        handler._output_tokens = out_tok
        estimated_tokens = handler.get_estimated_output_tokens()
        is_final = False
        thinking_active = handler.is_thinking_active()
        thinking_done = handler.is_thinking_done()

        # Yield progressively: text and thinking on every event so the caller
        # can display them in real-time. tool_calls remain None until is_final.
        yield text, thinking, None, False, thinking_active, thinking_done, estimated_tokens

    # Final yield with tool calls and usage
    in_tok, out_tok = handler.get_usage()
    is_final = True
    thinking_active = handler.is_thinking_active()
    thinking_done = handler.is_thinking_done()
    estimated_tokens = out_tok  # At final, use actual output tokens
    # Store on handler AND on function for backward compatibility
    handler._input_tokens = in_tok
    handler._output_tokens = out_tok
    stream_one_turn._last_usage = in_tok + out_tok
    yield handler.get_text(), handler.get_thinking(), pending_tool_calls, True, thinking_active, thinking_done, estimated_tokens


def execute_tool_calls(
    pending_tool_calls: list[dict],
    messages: list[dict],
    handler: StreamHandler,
    tool_calls_indexed: bool = False,
) -> tuple[list[dict], list[dict], bool]:
    """Execute a list of pending tool calls and return results.

    Returns (tool_results, new_tool_calls, tool_calls_indexed).
    """
    tool_results = []
    new_tool_calls: list[dict] = []
    hook_runner = _get_hook_runner()

    # --- Tool Reflection: track stats ---
    reflection = None
    try:
        from draguniteus.tools.reflection import get_tool_reflection
        reflection = get_tool_reflection()
    except Exception:
        pass

    # --- Nested Tool Executor for MCP ---
    nested_executor = None
    if getattr(handler, "_nested_tool_enabled", True):
        try:
            from draguniteus.tools.nested_tool_executor import NestedToolExecutor
            from draguniteus.tools.mcp_tools import tool_mcp_call as mcp_call_fn
            nested_executor = NestedToolExecutor(
                max_depth=getattr(handler, "_nested_tool_max_depth", 5),
                tool_map=dict(TOOL_MAP),
                mcp_tool_func=mcp_call_fn,
            )
        except Exception:
            pass

    # --- Self-Correction Engine ---
    self_correction = None
    try:
        from draguniteus.self_correction import get_self_correction_engine
        self_correction = get_self_correction_engine()
    except Exception:
        pass

    # --- Parallel execution for independent read-only tools ---
    # Tools that are read-only and have no side effects — safe to parallelize
    _PARALLELIZABLE_TOOLS = frozenset(["Read", "Glob", "Grep", "WebSearch", "WebFetch", "InspectEnvironment"])

    parallel_tcs = []
    sequential_tcs = []
    for tc in pending_tool_calls:
        name = tc.get("name", "")
        if name in _PARALLELIZABLE_TOOLS and not name.startswith("mcp__"):
            parallel_tcs.append(tc)
        else:
            sequential_tcs.append(tc)

    def _exec_one(tc: dict, ne: Any) -> dict:
        """Execute a single tool call. Extracted for ThreadPoolExecutor."""
        name = tc.get("name", "")
        args = tc.get("args", "")
        import json
        try:
            parsed = json.loads(args) if args else {}
        except json.JSONDecodeError:
            parsed = {"raw": args}

        if name.startswith("mcp__"):
            if ne:
                try:
                    result = ne._call_mcp_tool(
                        type("Node", (), {"name": name, "args": parsed, "depth": 0, "id": name})()
                    )
                except Exception as e:
                    result = f"MCP tool error: {e}"
            else:
                result = f"MCP tool error: nested executor not available"
            return {"tool": name, "result": result, "success": not str(result or "").startswith("MCP tool error"), "parsed": parsed}

        tool_fn = TOOL_MAP.get(name)
        if tool_fn:
            try:
                result = tool_fn(**parsed)
            except Exception as e:
                result = f"Tool error: {e}"
        else:
            result = f"Unknown tool: {name}"

        return {
            "tool": name,
            "result": result,
            "success": result and not str(result).startswith("Tool error") and not str(result).startswith("Unknown tool"),
            "parsed": parsed,
        }

    # Execute parallel group via ThreadPoolExecutor
    if len(parallel_tcs) > 1:
        results_map: dict[int, dict] = {}
        with ThreadPoolExecutor(max_workers=min(len(parallel_tcs), 4)) as pool:
            futures = {pool.submit(_exec_one, tc, nested_executor): i for i, tc in enumerate(parallel_tcs)}
            for fut in as_completed(futures):
                idx = futures[fut]
                try:
                    results_map[idx] = fut.result()
                except Exception as e:
                    results_map[idx] = {"tool": parallel_tcs[idx].get("name", "?"),
                                       "result": f"Thread error: {e}", "success": False, "parsed": {}}

        for i, tc in enumerate(parallel_tcs):
            r = results_map.get(i, {"tool": tc.get("name", "?"), "result": "", "success": False, "parsed": {}})
            tool_results.append({"tool": r["tool"], "result": r["result"], "success": r["success"]})
            if reflection:
                reflection.record_result(r["tool"], r["success"], str(r["result"])[:200] if not r["success"] else "")
            if self_correction and tc.get("name") in ("Write", "Edit"):
                try:
                    fp = r["parsed"].get("file_path", "")
                    content = r["parsed"].get("content", "")
                    if content and fp:
                        self_correction.record_write(fp, content, tc.get("name"))
                except Exception:
                    pass

    elif parallel_tcs:
        # Single parallel tool — run in-thread, no ThreadPool needed
        tc = parallel_tcs[0]
        r = _exec_one(tc, nested_executor)
        tool_results.append({"tool": r["tool"], "result": r["result"], "success": r["success"]})
        if reflection:
            reflection.record_result(r["tool"], r["success"], str(r["result"])[:200] if not r["success"] else "")

    # Execute sequential tools in order (Write/Edit/Bash/Git must be serial for correctness)
    for tc in sequential_tcs:
        name = tc.get("name")
        args = tc.get("args", "")
        import json
        try:
            parsed = json.loads(args) if args else {}
        except json.JSONDecodeError:
            parsed = {"raw": args}

        _track_tool_files(name, parsed)

        if reflection:
            reflection.record_start(name)

        result = None

        # MCP tool call — use nested executor if available
        if name.startswith("mcp__"):
            if nested_executor:
                try:
                    result = nested_executor._call_mcp_tool(
                        type("Node", (), {"name": name, "args": parsed, "depth": 0, "id": name})()
                    )
                except Exception as e:
                    result = f"MCP tool error: {e}"
            else:
                parts = name.split("__", 2)
                if len(parts) == 3:
                    try:
                        from draguniteus.tools.mcp_tools import tool_mcp_call
                        result = tool_mcp_call(name, parsed)
                    except Exception as e:
                        result = f"MCP tool error: {e}"
                else:
                    result = f'MCP error: invalid tool name format "{name}"'

            success = not str(result or "").startswith("MCP tool error")
            if reflection:
                reflection.record_result(name, success, str(result)[:200] if not success else "")
            tool_results.append({"tool": name, "result": result, "success": success})

            if self_correction and name in ("Write", "Edit"):
                try:
                    file_path = parsed.get("file_path", "")
                    content = parsed.get("content", "")
                    if content and file_path:
                        self_correction.record_write(file_path, content, name)
                except Exception:
                    pass
            continue

        tool_fn = TOOL_MAP.get(name)
        if tool_fn:
            hook_result = hook_runner.run_prettooluse(name, parsed, args)
            blocked = False
            if hook_result:
                blocked = hook_result.get("block", False)
                system_msg = hook_result.get("systemMessage", "")
                if blocked:
                    result = f"[BLOCKED by hook] {system_msg}"
                elif system_msg:
                    warn_msg = system_msg
                    try:
                        exec_result = tool_fn(**parsed)
                        result = f"{warn_msg}\n\n{exec_result}"
                    except Exception as e:
                        result = f"Tool error: {e}"
                else:
                    try:
                        result = tool_fn(**parsed)
                    except Exception as e:
                        result = f"Tool error: {e}"
            else:
                try:
                    result = tool_fn(**parsed)
                except Exception as e:
                    result = f"Tool error: {e}"
        else:
            result = f"Unknown tool: {name}"

        success = result and not str(result).startswith("Tool error") and not str(result).startswith("Unknown tool")
        if reflection:
            reflection.record_result(name, success, str(result)[:200] if not success else "")

        tool_results.append({"tool": name, "result": result, "success": success})

        try:
            hook_runner.run_posttooluse(name, parsed, str(result))
        except Exception:
            pass

        # Git auto-commit after Write/Edit if enabled
        if name in ("Write", "Edit") and getattr(config, "git_auto_commit_enabled", False):
            try:
                from draguniteus.tools.git import tool_git_auto_commit
                import os
                file_path = parsed.get("file_path", "")
                if file_path and os.path.exists(file_path):
                    commit_result = tool_git_auto_commit()
                    if commit_result and "No changes" not in commit_result:
                        tool_results.append({"tool": "GitAutoCommit", "result": commit_result, "success": True})
            except Exception:
                pass

        if self_correction and name in ("Write", "Edit"):
            try:
                file_path = parsed.get("file_path", "")
                content = parsed.get("content", "")
                if content and file_path:
                    self_correction.record_write(file_path, content, name)
            except Exception:
                pass

        if not tool_calls_indexed:
            tool_calls_indexed = True
            try:
                from draguniteus.memory.pattern_library import _get_pattern_library
                lib = _get_pattern_library()
                tool_names = [t.get("name", "") for t in pending_tool_calls]
                code_content = ""
                language = "text"
                for tr in tool_results:
                    res = str(tr.get("result", ""))
                    if "```" in res:
                        parts = res.split("```")
                        for i in range(1, len(parts), 2):
                            if parts[i].strip():
                                code_content = parts[i].strip()
                                if "python" in tool_names or "python" in res:
                                    language = "python"
                                elif "javascript" in tool_names or "js" in res:
                                    language = "javascript"
                                elif "typescript" in tool_names or "ts" in res:
                                    language = "typescript"
                                break
                    if code_content:
                        break
            except Exception:
                pass

        messages.append({
            "role": "assistant",
            "content": [{"type": "tool_use", "name": name, "input": parsed}]
        })
        messages.append({
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": tc.get("id", ""), "content": str(result)}]
        })

    return tool_results, new_tool_calls, tool_calls_indexed


def run_one_turn(
    client: DraguniteusClient,
    messages: list[dict],
    system: str | None,
    config: Config,
    full_drama: bool = True,
) -> tuple[str, list[dict], int, int, str]:
    """Run a single agent turn with streaming (fully buffered, for backward compat).

    Returns (text_response, tool_results, input_tokens, output_tokens, thinking).
    """
    tools = client.get_tool_schemas()
    console = _console
    handler = StreamHandler(console, full_drama)

    # --- Thinking Router ---
    routing = {"thinking": False}
    if getattr(config, "thinking_router_enabled", True):
        try:
            from draguniteus.thinking_router import get_thinking_router
            router = get_thinking_router()
            routing = router.route(messages, system or "")
            if routing.get("thinking") and router:
                betas = router.compute_betas([], routing)
            else:
                betas = []
        except Exception:
            betas = []
    else:
        effort_settings = config.get_effort_settings()
        betas = effort_settings.get("betas", [])

    # --- Developer Role ---
    if getattr(config, "developer_role_enabled", True):
        try:
            from draguniteus.role_adapter import get_role_adapter
            adapter = get_role_adapter()
            adapter.set_tracked_files(get_tracked_files() or [])
            developer_content = adapter.build_developer_message_for_turn(
                messages=messages,
                tools=tools,
                tracked_files=get_tracked_files(),
            )
            if developer_content:
                system = (system or "") + "\n\n[Developer Context]\n" + developer_content
        except Exception:
            pass

    stream = client.stream(
        messages=messages,
        tools=tools,
        system=system,
        betas=betas,
    )

    pending_tool_calls: list[dict] = []
    tool_calls_indexed = False

    for event in stream:
        handler.handle_event(event)

    pending_tool_calls = handler.get_tool_calls()
    initial_text = handler.get_text() if pending_tool_calls else ""

    tool_results = []
    if pending_tool_calls:
        tool_results, _, tool_calls_indexed = execute_tool_calls(
            pending_tool_calls, messages, handler, tool_calls_indexed
        )

        # --- Self-Correction: verify Write/Edit results ---
        if getattr(config, "self_improvement_enabled", True):
            try:
                from draguniteus.self_correction import get_self_correction_engine
                engine = get_self_correction_engine()
                needs_fix, verif_results, injected_msg = engine.check_and_fix(messages)
                if needs_fix and injected_msg:
                    # Inject error context so the next streaming pass addresses the fix
                    messages.append({"role": "user", "content": injected_msg})
            except Exception:
                pass

        stream2 = client.stream(messages=messages, tools=tools, system=system, betas=betas)
        handler2 = StreamHandler(console, full_drama)
        for event in stream2:
            handler2.handle_event(event)

        text = handler2.get_text()
        in_tok2, out_tok2 = handler2.get_usage()
        handler._input_tokens += in_tok2
        handler._output_tokens += out_tok2
    else:
        text = handler.get_text()

    thinking = handler.get_thinking()
    # The logic: prefer follow-up text (handler2) if non-empty, else initial_text.
    # - No tools: initial_text="", text=handler's text -> use text
    # - Tools + follow-up: initial_text="...Done!", text=handler2's text -> use text
    # - Tools + no follow-up: initial_text="...Done!", text="" -> use initial_text
    final_text = text if text else initial_text
    # If self-correction fired (handler2 created), use handler2's thinking
    # since it reflects the actual fix the model just applied
    if pending_tool_calls and text:
        thinking = handler2.get_thinking()
    return final_text, tool_results, handler._input_tokens, handler._output_tokens, thinking


def run_agent_loop(
    messages: list[dict],
    system: str | None,
    config: Config,
    full_drama: bool = True,
) -> Iterator[str]:
    """Main loop: stream text tokens as they arrive."""
    tools = config.get_tool_schemas() if hasattr(config, 'get_tool_schemas') else client.get_tool_schemas()
    console = _console

    with Live(console=console, refresh_per_second=10) as live:
        stream = client.stream(messages=messages, tools=tools, system=system)
        handler = StreamHandler(console, full_drama)

        for event in stream:
            result = handler.handle_event(event)
            if result:
                pass

            text = handler.get_text()
            if text:
                md = Markdown(text)
                live.update(md)

        final_text = handler.get_text()
        live.update(Markdown(final_text) if final_text else Text(""))

    return final_text