"""Main agent loop: handles streaming, tool dispatch, and response rendering."""
from __future__ import annotations

import time
from typing import Any, Iterator

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown

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

    def __init__(self, console: Console, full_drama: bool = True):
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
        import anthropic

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
                elif btype == "thinking":
                    self._thinking_parts = []

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
            elif dtype == "input_json_delta":
                arg_text = getattr(delta, "partial_json", "")
                if self._current_tool is not None:
                    self._current_tool["args"] += arg_text
                return None

        # Content block stop
        elif event_type == "content_block_stop":
            if self._current_tool:
                tc = self._current_tool
                self._current_tool = None
                return tc

        # Message delta (final tokens)
        elif event_type == "message_delta":
            delta = getattr(event, "delta", None)
            if delta:
                # trailing token
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

    def get_tool_calls(self) -> list[dict]:
        return self._tool_calls


def run_one_turn(
    client: DraguniteusClient,
    messages: list[dict],
    system: str | None,
    config: Config,
    full_drama: bool = True,
) -> tuple[str, list[dict], int, int, str]:
    """Run a single agent turn with streaming.

    Returns (text_response, tool_results, input_tokens, output_tokens, thinking).
    Token counts are the sum of all API calls in this turn.
    Thinking is the raw thinking content from extended thinking.
    """
    tools = client.get_tool_schemas()
    console = _console
    handler = StreamHandler(console, full_drama)

    # Get effort-based settings
    effort_settings = config.get_effort_settings()
    betas = effort_settings.get("betas", [])

    # Stream response
    stream = client.stream(
        messages=messages,
        tools=tools,
        system=system,
        betas=betas,
    )

    start_time = time.time()
    pending_tool_calls: list[dict] = []
    tool_calls_indexed = False

    for event in stream:
        handler.handle_event(event)

    elapsed = time.time() - start_time

    # Get tool calls collected during streaming (handle_event returns tool calls on content_block_stop)
    pending_tool_calls = handler.get_tool_calls()

    # Capture initial response text BEFORE executing tools (for display before tool output)
    initial_text = handler.get_text() if pending_tool_calls else ""

    # If we have tool calls to execute
    tool_results = []
    if pending_tool_calls:
        for tc in pending_tool_calls:
            name = tc.get("name")
            args = tc.get("args", "")
            # Parse args from JSON
            import json
            try:
                parsed = json.loads(args) if args else {}
            except json.JSONDecodeError:
                parsed = {"raw": args}

            # Track files touched by this tool for rules injection
            _track_tool_files(name, parsed)

            # Execute tool
            result = None
            hook_runner = _get_hook_runner()

            # Check if it's an MCP tool call (mcp__server__tool pattern)
            if name.startswith("mcp__"):
                parts = name.split("__", 2)
                if len(parts) == 3:
                    _, server_name, mcp_tool_name = parts
                    try:
                        from draguniteus.tools.mcp_tools import tool_mcp_call
                        result = tool_mcp_call(name, parsed)
                    except Exception as e:
                        result = f"MCP tool error: {e}"
                else:
                    result = f'MCP error: invalid tool name format "{name}"'
                tool_results.append({"tool": name, "result": result})
                continue

            tool_fn = TOOL_MAP.get(name)
            if tool_fn:
                # Run PreToolUse hooks
                hook_result = hook_runner.run_prettooluse(name, parsed, args)
                blocked = False
                if hook_result:
                    blocked = hook_result.get("block", False)
                    system_msg = hook_result.get("systemMessage", "")
                    if blocked:
                        result = f"[BLOCKED by hook] {system_msg}"
                    elif system_msg:
                        # Warn but proceed
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

            tool_results.append({
                "tool": name,
                "result": result,
            })

            # Run PostToolUse hooks
            try:
                hook_runner = _get_hook_runner()
                hook_runner.run_posttooluse(name, parsed, str(result))
            except Exception:
                pass

            # Learn from successful tool sequence (after all tools complete)
            if not tool_calls_indexed:
                tool_calls_indexed = True
                try:
                    from draguniteus.memory.pattern_library import _get_pattern_library
                    lib = _get_pattern_library()
                    tool_names = [tc.get("name", "") for tc in tool_calls]
                    # Extract code-like content from tool results
                    code_content = ""
                    language = "text"
                    for tr in tool_results:
                        res = str(tr.get("result", ""))
                        # Look for code blocks
                        if "```" in res:
                            # Extract first code block
                            parts = res.split("```")
                            for i in range(1, len(parts), 2):
                                if parts[i].strip():
                                    code_content = parts[i].strip()
                                    # Try to detect language from tool name or result
                                    if "python" in tool_names or "python" in res:
                                        language = "python"
                                    elif "javascript" in tool_names or "javascript" in res or "js" in res:
                                        language = "javascript"
                                    elif "typescript" in tool_names or "typescript" in res or "ts" in res:
                                        language = "typescript"
                                    break
                        if code_content:
                            break
                    if tool_names and (code_content or text):
                        lib.learn_from_tool_sequence(
                            tool_names=tool_names,
                            code=code_content or text[:500],
                            language=language,
                            task=text[:200] if text else " ".join(tool_names),
                        )
                except Exception:
                    pass

            # Re-call model with tool result
            messages.append({
                "role": "assistant",
                "content": [{"type": "tool_use", "name": name, "input": parsed}]
            })
            messages.append({
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": tc.get("id", ""), "content": str(result)}]
            })

        # Get follow-up response
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

    # Return initial response text when tools were called (shows what model said before tools)
    return initial_text or text, tool_results, handler._input_tokens, handler._output_tokens, thinking


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
                # tool call — handled in run_one_turn
                pass

            # Render current text as markdown
            text = handler.get_text()
            if text:
                md = Markdown(text)
                live.update(md)

        final_text = handler.get_text()
        live.update(Markdown(final_text) if final_text else Text(""))

    return final_text