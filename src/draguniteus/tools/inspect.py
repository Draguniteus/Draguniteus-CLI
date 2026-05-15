"""Inspect tool — let Draguniteus examine its own environment."""
from __future__ import annotations

from typing import Any

INSPECT_TOOLS: list[dict[str, Any]] = [
    {
        "name": "InspectEnvironment",
        "description": "Examine Draguniteus's own environment — config, tools, hooks, permissions, git context, MCP servers, skills, and more. Use this when you need to understand what tools and settings are available, or to diagnose why something isn't working.",
        "input_schema": {
            "type": "object",
            "properties": {
                "section": {
                    "type": "string",
                    "description": "Specific section to inspect: self, config, env, git, session, tools, hooks, permissions, mcp, skills, pattern_library, archive. If omitted, returns all sections.",
                },
                "as_json": {
                    "type": "boolean",
                    "default": False,
                    "description": "Return output as machine-readable JSON instead of human-readable text."
                }
            }
        }
    },
]


def tool_inspect_environment(section: str | None = None, as_json: bool = False, **kwargs) -> str:
    """Inspect Draguniteus's own environment."""
    try:
        from draguniteus.inspect import get_full_environment, format_environment
        env = get_full_environment()

        if as_json:
            import json
            if section:
                return json.dumps(env.get(section, {}), indent=2)
            return json.dumps(env, indent=2)

        return format_environment(env, section=section)
    except Exception as e:
        return f"Inspect error: {e}"