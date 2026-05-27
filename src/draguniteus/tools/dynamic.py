"""Dynamic tool creation — register custom tools at runtime.

Tools are stored in .draguniteus/custom_tools/ as JSON schemas
and loaded into TOOL_MAP on startup.
"""
from __future__ import annotations

import json
import os
import platform
from pathlib import Path
from typing import Any

from draguniteus.config import DEFAULT_CONFIG_DIR


def _get_config_dir() -> Path:
    if platform.system() == "Windows":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path.home()
    return base / ".draguniteus"


CUSTOM_TOOLS_DIR = _get_config_dir() / "custom_tools"


class ToolBuilder:
    """Builds and registers custom tools dynamically."""

    def __init__(self):
        self._tools: dict[str, dict[str, Any]] = {}
        self._handlers: dict[str, callable] = {}
        CUSTOM_TOOLS_DIR.mkdir(parents=True, exist_ok=True)

    def create_tool(
        self,
        name: str,
        description: str,
        input_schema: dict[str, Any],
        handler_fn: callable,
        tags: list[str] | None = None,
    ) -> str:
        """Create and register a new tool.

        Args:
            name: tool name (e.g., "my_custom_tool")
            description: human-readable description
            input_schema: Anthropic-style input schema
            handler_fn: function to call when tool is invoked
            tags: optional tags for categorization

        Returns:
            The tool name that was registered.
        """
        if name in self._handlers:
            return f"Tool '{name}' already exists"

        tool_schema = {
            "name": name,
            "description": description,
            "input_schema": input_schema,
            "tags": tags or [],
        }

        self._tools[name] = tool_schema
        self._handlers[name] = handler_fn

        # Persist to disk
        self._save_tool(name, tool_schema)

        # Try to register in global TOOL_MAP
        try:
            from draguniteus.tools import TOOL_MAP
            TOOL_MAP[name] = handler_fn
        except Exception:
            pass

        return name

    def _save_tool(self, name: str, schema: dict[str, Any]) -> None:
        """Save tool schema to disk."""
        path = CUSTOM_TOOLS_DIR / f"{name}.json"
        try:
            path.write_text(json.dumps(schema, indent=2), encoding="utf-8")
        except Exception:
            pass

    def load_tools(self) -> dict[str, dict[str, Any]]:
        """Load all custom tools from disk."""
        if not CUSTOM_TOOLS_DIR.exists():
            return {}
        for path in CUSTOM_TOOLS_DIR.glob("*.json"):
            try:
                schema = json.loads(path.read_text(encoding="utf-8"))
                name = schema.get("name", path.stem)
                self._tools[name] = schema
            except Exception:
                continue
        return self._tools

    def get_tool_schema(self, name: str) -> dict[str, Any] | None:
        """Get the schema for a registered tool."""
        return self._tools.get(name)

    def get_handler(self, name: str) -> callable | None:
        """Get the handler function for a tool."""
        return self._handlers.get(name)

    def list_tools(self) -> list[str]:
        """List all registered custom tool names."""
        return list(self._tools.keys())

    def delete_tool(self, name: str) -> bool:
        """Delete a custom tool."""
        if name in self._tools:
            del self._tools[name]
        if name in self._handlers:
            del self._handlers[name]
        try:
            from draguniteus.tools import TOOL_MAP
            if name in TOOL_MAP:
                del TOOL_MAP[name]
        except Exception:
            pass
        path = CUSTOM_TOOLS_DIR / f"{name}.json"
        if path.exists():
            try:
                path.unlink()
            except Exception:
                pass
        return True


# Global builder instance
_tool_builder: ToolBuilder | None = None


def get_tool_builder() -> ToolBuilder:
    global _tool_builder
    if _tool_builder is None:
        _tool_builder = ToolBuilder()
        _tool_builder.load_tools()
    return _tool_builder


def register_custom_tool(
    name: str,
    description: str,
    input_schema: dict[str, Any],
    handler_fn: callable,
) -> str:
    """Convenience: create and register a custom tool."""
    return get_tool_builder().create_tool(name, description, input_schema, handler_fn)
