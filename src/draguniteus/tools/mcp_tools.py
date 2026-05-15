"""MCP tool wrapper: bridges MCP tools to the Anthropic function-calling interface."""
from __future__ import annotations

from typing import Any

# Lazy-initialized global MCP client
_mcp_client: Any = None
_mcp_schemas_built: bool = False
_mcp_tool_schemas: list[dict[str, Any]] = []


def get_mcp_client() -> Any:
    """Get or create the global MCPClient instance."""
    global _mcp_client
    if _mcp_client is None:
        from draguniteus.tools.mcp import MCPClient
        _mcp_client = MCPClient()
    return _mcp_client


def build_mcp_tool_schemas() -> list[dict[str, Any]]:
    """Build Anthropic tool schemas for all started MCP servers.

    Returns a list of tool definitions with names like mcp__<server>__<tool>.
    Each server's tools are discovered via the tools/list MCP protocol call.
    """
    global _mcp_tool_schemas, _mcp_schemas_built

    if _mcp_schemas_built:
        return _mcp_tool_schemas

    client = get_mcp_client()

    for server_name in list(client.servers.keys()):
        # Ensure server is started
        if server_name not in client._processes:
            client.start_server(server_name)

        tools = client.list_tools(server_name)
        for tool in tools:
            tool_name = tool.get("name", "")
            if not tool_name:
                continue

            mcp_name = f"mcp__{server_name}__{tool_name}"
            description = tool.get("description", f"MCP tool {tool_name} on {server_name} server")
            input_schema = tool.get("inputSchema", {"type": "object", "properties": {}})

            # Handle structured input schemas from MCP
            if "properties" not in input_schema:
                input_schema = {"type": "object", "properties": {}}

            _mcp_tool_schemas.append({
                "name": mcp_name,
                "description": description,
                "input_schema": input_schema,
                "_server": server_name,
                "_tool": tool_name,
            })

    _mcp_schemas_built = True
    return _mcp_tool_schemas


def tool_mcp_call(tool_name: str, arguments: dict[str, Any]) -> str:
    """Dispatch an MCP tool call to the appropriate server.

    Args:
        tool_name: Full MCP tool name like "mcp__gmail__create_draft"
        arguments: Dict of tool arguments

    Returns:
        JSON string with tool result or error
    """
    # Parse mcp__server__tool pattern
    parts = tool_name.split("__", 2)
    if len(parts) != 3:
        return f'MCP error: invalid tool name format "{tool_name}"'

    _, server_name, mcp_tool_name = parts

    client = get_mcp_client()

    if server_name not in client.servers:
        return f'MCP error: unknown server "{server_name}"'

    # Ensure server is started before calling
    if server_name not in client._processes:
        client.start_server(server_name)

    try:
        result = client.call_tool(server_name, mcp_tool_name, arguments)
        return result
    except Exception as e:
        return f"MCP error calling {tool_name}: {e}"


def reset_mcp_cache() -> None:
    """Reset the MCP schema cache (forces re-discovery on next call)."""
    global _mcp_schemas_built, _mcp_tool_schemas
    _mcp_schemas_built = False
    _mcp_tool_schemas = []
