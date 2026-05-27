"""Nested tool calling with retry, depth limiting, and MCP server recovery.

Provides:
  - ToolCallNode: single call with args, status, dependencies
  - NestedToolExecutor: manages execution graph with 5-level depth limit
  - RetryPolicy: transient vs permanent error classification
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from draguniteus.theming import CYAN, DIM, RESET


@dataclass
class ToolCallNode:
    """A single tool call with its execution state."""
    name: str
    args: dict[str, Any]
    depth: int = 0
    status: str = "pending"  # pending, running, success, failed, retrying
    result: Any = None
    error: str = ""
    attempts: int = 0
    parent_id: str | None = None
    id: str = ""


@dataclass
class RetryPolicy:
    """Retry configuration for transient errors."""
    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 10.0
    multiplicative: bool = True


TRANSIENT_ERROR_PATTERNS = frozenset([
    "timeout", "timed out", "connection refused", "temporarily unavailable",
    "rate limit", "too many requests", "server busy", "try again",
    "503", "502", "429", "ECONNRESET", "ETIMEDOUT",
])

PERMANENT_ERROR_PATTERNS = frozenset([
    "not found", "invalid", "not permitted", "permission denied",
    "does not exist", "unauthorized", "forbidden", "400", "401", "403", "404",
    "server_not_initialized", "method_not_found",
])


class NestedToolExecutor:
    """Executes tool calls with depth limiting, retry, and MCP recovery."""

    def __init__(
        self,
        max_depth: int = 5,
        retry_policy: RetryPolicy | None = None,
        tool_map: dict[str, callable] | None = None,
        mcp_tool_func: callable | None = None,
    ):
        self.max_depth = max_depth
        self.retry_policy = retry_policy or RetryPolicy()
        self.tool_map = tool_map or {}
        self.mcp_tool_func = mcp_tool_func
        self._call_stack: list[str] = []  # tool call IDs in current stack
        self._results: dict[str, Any] = {}  # id -> result

    def execute(
        self,
        tool_calls: list[dict[str, Any]],
        parent_id: str | None = None,
        depth: int = 0,
    ) -> list[dict[str, Any]]:
        """Execute a list of tool calls, handling nesting recursively.

        Returns list of result dicts with {id, name, status, result, error, depth}.
        """
        results = []
        for tc in tool_calls:
            node_id = f"{tc.get('name', '?')}_{depth}_{tc.get('id', id(tc))}"
            node = ToolCallNode(
                name=tc.get("name", ""),
                args=tc.get("input", tc.get("args", {})),
                depth=depth,
                parent_id=parent_id,
                id=node_id,
            )

            if depth >= self.max_depth:
                node.status = "failed"
                node.error = f"Max nesting depth ({self.max_depth}) reached"
                self._print_nested_start(node)
                self._print_nested_result(node)
                results.append(self._node_to_dict(node))
                continue

            # Execute with retry
            result = self._execute_with_retry(node)
            results.append(result)

        return results

    def _execute_with_retry(self, node: ToolCallNode) -> dict[str, Any]:
        """Execute a single node with retry logic."""
        self._print_nested_start(node)

        while node.attempts < self.retry_policy.max_attempts:
            node.attempts += 1
            node.status = "running"

            try:
                if node.name.startswith("mcp__") and self.mcp_tool_func:
                    # MCP tool call
                    node.result = self._call_mcp_tool(node)
                elif node.name in self.tool_map:
                    node.result = self.tool_map[node.name](**node.args)
                else:
                    node.status = "failed"
                    node.error = f"Unknown tool: {node.name}"
                    break

                node.status = "success"
                break

            except Exception as e:
                err_str = str(e)
                node.error = err_str

                if self._is_transient_error(err_str) and node.attempts < self.retry_policy.max_attempts:
                    node.status = "retrying"
                    delay = self._compute_delay(node.attempts)
                    time.sleep(delay)
                    continue
                else:
                    node.status = "failed"
                    break

        self._print_nested_result(node)
        return self._node_to_dict(node)

    def _call_mcp_tool(self, node: ToolCallNode) -> Any:
        """Call an MCP tool with server recovery on crash."""
        if self.mcp_tool_func:
            return self.mcp_tool_func(node.name, node.args)
        raise RuntimeError(f"MCP tool called but mcp_tool_func not set: {node.name}")

    def _is_transient_error(self, error: str) -> bool:
        """Classify error as transient (retry) vs permanent (fail fast)."""
        err_lower = error.lower()
        for pattern in PERMANENT_ERROR_PATTERNS:
            if pattern in err_lower:
                return False
        for pattern in TRANSIENT_ERROR_PATTERNS:
            if pattern in err_lower:
                return True
        return False

    def _compute_delay(self, attempt: int) -> float:
        """Compute retry delay with exponential backoff."""
        policy = self.retry_policy
        if policy.multiplicative:
            delay = policy.base_delay * (2 ** (attempt - 1))
        else:
            delay = policy.base_delay * attempt
        return min(delay, policy.max_delay)

    def _print_nested_start(self, node: ToolCallNode) -> None:
        """Print nested tool start with depth indentation."""
        if node.depth == 0:
            return
        try:
            import sys
            indent = "  " * node.depth
            arrow = "└─" if node.depth == 1 else "│  " * (node.depth - 1) + "└─"
            msg = f"{indent}{arrow} {node.name}"
            sys.stdout.buffer.write(f"{CYAN}{msg}{RESET}\n".encode('utf-8', errors='replace'))
            sys.stdout.buffer.flush()
        except Exception:
            pass

    def _print_nested_result(self, node: ToolCallNode) -> None:
        """Print nested tool result."""
        if node.depth == 0:
            return
        try:
            import sys
            indent = "  " * node.depth
            if node.status == "success":
                result_short = str(node.result)[:80] if node.result else "ok"
                msg = f"{indent}  ✓ {result_short}"
                sys.stdout.buffer.write(f"{DIM}{msg}{RESET}\n".encode('utf-8', errors='replace'))
            elif node.status == "failed":
                err_short = node.error[:100] if node.error else "failed"
                msg = f"{indent}  ✗ {err_short}"
                sys.stdout.buffer.write(f"{DIM}{msg}{RESET}\n".encode('utf-8', errors='replace'))
            sys.stdout.buffer.flush()
        except Exception:
            pass

    @staticmethod
    def _node_to_dict(node: ToolCallNode) -> dict[str, Any]:
        return {
            "id": node.id,
            "name": node.name,
            "depth": node.depth,
            "status": node.status,
            "result": node.result,
            "error": node.error,
            "attempts": node.attempts,
            "parent_id": node.parent_id,
        }
