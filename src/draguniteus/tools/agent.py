"""Agent tool — spawn sub-agents for specialized tasks."""
from __future__ import annotations

import json
import time
import uuid
from typing import Any

from draguniteus.subagents import load_agent, list_agents


def _run_subagent_loop(
    agent_def: dict[str, Any],
    query: str,
    config: Any,
) -> dict[str, Any]:
    """Actually execute a sub-agent with full tool access.

    Runs a nested agent loop: the sub-agent can call tools, and those tools
    execute in the context of the parent agent. Returns when the sub-agent
    produces a final text response (no more tool calls).

    Args:
        agent_def: Loaded agent definition from load_agent()
        query: The task/query to give the sub-agent
        config: Config object for API settings

    Returns:
        {"text": "...", "tool_results": [...], "agent": "...", "model": "..."}
    """
    from draguniteus.client import DraguniteusClient
    from draguniteus.agent import StreamHandler
    from draguniteus.tools import TOOL_MAP

    client = DraguniteusClient(config)
    tools = client.get_tool_schemas()

    # Build system prompt from agent definition
    agent_system = agent_def.get("system_prompt", "")
    system_override = f"{agent_system}\n\nYou are performing a sub-task delegated to you by another agent. Focus solely on completing this task." if agent_system else None

    # Build initial message with the query
    messages = [
        {
            "role": "user",
            "content": query,
        }
    ]

    tool_results = []
    max_subagent_turns = 10  # Prevent infinite loops

    for turn in range(max_subagent_turns):
        # Stream response from sub-agent
        stream = client.stream(
            messages=messages,
            tools=tools,
            system=system_override,
        )

        handler = StreamHandler(None, False)  # silent - we capture output
        for event in stream:
            handler.handle_event(event)

        # Collect tool calls
        pending_tool_calls = handler.get_tool_calls()

        if not pending_tool_calls:
            # No tool calls - this is the final response
            text = handler.get_text()
            return {
                "text": text or f"[{agent_def['name']}] No response generated",
                "tool_results": tool_results,
                "agent": agent_def["name"],
                "model": agent_def.get("model", "inherit"),
                "turns": turn + 1,
            }

        # Execute each tool call
        for tc in pending_tool_calls:
            name = tc.get("name", "")
            args_raw = tc.get("args", "")

            # Parse args from JSON
            try:
                parsed = json.loads(args_raw) if args_raw else {}
            except json.JSONDecodeError:
                parsed = {"raw": args_raw}

            # Execute tool (same as in agent.py)
            tool_fn = TOOL_MAP.get(name)
            if tool_fn:
                try:
                    result = tool_fn(**parsed)
                except Exception as e:
                    result = f"Tool error: {e}"
            else:
                result = f"Unknown tool: {name}"

            # Handle tool result - convert to string
            if not isinstance(result, str):
                result = json.dumps(result) if isinstance(result, dict) else str(result)

            tool_results.append({
                "tool": name,
                "input": parsed,
                "output": result[:500],  # Truncate long outputs
            })

            # Append to messages
            messages.append({
                "role": "assistant",
                "content": [{"type": "tool_use", "name": name, "input": parsed}]
            })
            messages.append({
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": tc.get("id", ""), "content": str(result)[:500]}]
            })

    # Hit max turns - return what we have
    return {
        "text": f"[{agent_def['name']}] Max sub-agent turns reached",
        "tool_results": tool_results,
        "agent": agent_def["name"],
        "model": agent_def.get("model", "inherit"),
        "turns": max_subagent_turns,
    }


def tool_agent(task_id: str = "", agent: str = "", query: str = "", **kwargs) -> str:
    """Spawn a sub-agent to handle a specialized task.

    The sub-agent runs with its own system prompt and returns a result.
    It can make tool calls (Read, Grep, Glob, etc.) which execute in your context.
    When it completes, SubagentStop hooks fire.

    Args:
        task_id: Unique ID for this subagent task (auto-generated if empty)
        agent: Agent name: explore, plan, review, debug, or custom agent name
        query: The task or question to give the sub-agent

    Returns:
        JSON string with status, result, agent name, and duration
    """
    start = time.time()

    if not task_id:
        task_id = str(uuid.uuid4())[:8]
    if not agent:
        return '{"status": "error", "error": "agent name required"}'
    if not query:
        return '{"status": "error", "error": "query required"}'

    # Load agent definition — exact name first, then query-based routing
    agent_def = load_agent(agent)

    # If exact name lookup failed, try query-based routing
    if not agent_def and agent:
        from draguniteus.subagents import route_query_to_agent
        agent_def = route_query_to_agent(query)
        if agent_def:
            agent_def["_routed"] = True  # Mark as query-routed

    if not agent_def:
        agents = list_agents()
        return json.dumps({
            "status": "error",
            "error": f"Unknown agent: {agent}",
            "available": [a["name"] for a in agents]
        })

    # Get config for API settings
    from draguniteus.config import Config
    config = Config()

    # Run the actual sub-agent
    try:
        result = _run_subagent_loop(agent_def, query, config)
    except Exception as e:
        result = {
            "text": f"[{agent_def['name']}] Error: {str(e)}",
            "tool_results": [],
            "agent": agent_def["name"],
            "model": agent_def.get("model", "inherit"),
            "error": str(e),
        }

    duration_ms = (time.time() - start) * 1000

    # Fire SubagentStop hook
    try:
        from draguniteus.hook_runner import get_hook_runner
        hook_runner = get_hook_runner()
        hook_runner.run_subagentstop(agent_def["name"], result.get("text", ""))
    except Exception:
        pass

    # Format output
    output_parts = []
    output_parts.append(f"[{agent_def['name']}] Task: {query[:60]}{'...' if len(query) > 60 else ''}")
    if result.get("tool_results"):
        output_parts.append(f"Tools used: {len(result['tool_results'])}")
        for tr in result["tool_results"][:5]:  # Show first 5 tools
            output_parts.append(f"  - {tr['tool']}: {tr.get('output', '')[:60]}...")
    if result.get("text"):
        output_parts.append(f"Result: {result['text'][:300]}{'...' if len(result.get('text', '')) > 300 else ''}")
    if result.get("error"):
        output_parts.append(f"Error: {result['error']}")

    return json.dumps({
        "status": "ok",
        "task_id": task_id,
        "result": "\n".join(output_parts),
        "full_result": result,
        "agent": agent_def["name"],
        "model": agent_def.get("model", "inherit"),
        "turns": result.get("turns", 1),
        "duration_ms": round(duration_ms, 1),
    })


AGENT_TOOLS = [
    {
        "name": "Agent",
        "description": """Spawn a specialized sub-agent to handle a task.

The sub-agent runs with its own system prompt and returns a result.
It can make tool calls (Read, Grep, Glob, Bash, etc.) which execute in your context.

Example:
- User asks to explore a codebase → spawn 'explore' agent
- User asks to debug an issue → spawn 'debug' agent
- User asks to plan architecture → spawn 'plan' agent

Agents have different specialties:
- explore: Deep code exploration and pattern finding
- plan: Architectural planning and strategy
- review: Code review with improvement suggestions
- debug: Systematic debugging and fix execution

The sub-agent will use tools on your behalf to complete the task.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Unique ID for this subagent task (auto-generated if empty)",
                },
                "agent": {
                    "type": "string",
                    "description": "Agent name: explore, plan, review, debug, or custom agent name",
                },
                "query": {
                    "type": "string",
                    "description": "The task or question to give the sub-agent",
                },
            },
            "required": ["agent", "query"],
        },
    },
]