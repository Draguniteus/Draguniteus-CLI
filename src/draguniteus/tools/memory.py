"""Memory tools: WriteDailyNote, ReadDailyNote, WriteProjectMemory, ReadProjectMemory."""
from __future__ import annotations

from typing import Any

from draguniteus.memory.manager import MemoryManager


MEMORY_TOOLS: list[dict[str, Any]] = [
    {
        "name": "WriteDailyNote",
        "description": "Write to today's daily memory file (memory/YYYY-MM-DD.md). "
                       "Use to record decisions, learnings, or context that should persist "
                       "but isn't appropriate for DRAGUNITEUS.md.",
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "Content to write to the daily note."
                }
            },
            "required": ["content"]
        }
    },
    {
        "name": "ReadDailyNote",
        "description": "Read today's daily memory file.",
        "input_schema": {
            "type": "object",
            "properties": {
                "date": {
                    "type": "string",
                    "description": "Date to read (YYYY-MM-DD). Defaults to today."
                }
            }
        }
    },
    {
        "name": "WriteProjectMemory",
        "description": "Write or overwrite the DRAGUNITEUS.md project memory file.",
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "Full content for DRAGUNITEUS.md."
                }
            },
            "required": ["content"]
        }
    },
    {
        "name": "ReadProjectMemory",
        "description": "Read the current DRAGUNITEUS.md project memory.",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    },
]


_memory = MemoryManager()


def tool_write_daily_note(content: str) -> str:
    """Write to today's daily memory."""
    _memory.project_memory.write_daily(content)
    return f"ok — wrote {len(content)} chars to today's daily note"


def tool_read_daily_note(date: str | None = None) -> str:
    """Read a daily note by date."""
    result = _memory.project_memory.read_daily(date)
    if result is None:
        return f"No daily note found for {date or 'today'}."
    return result


def tool_write_project_memory(content: str) -> str:
    """Write project memory (DRAGUNITEUS.md)."""
    _memory.project_memory.write(content)
    return f"ok — wrote {len(content)} chars to DRAGUNITEUS.md"


def tool_read_project_memory() -> str:
    """Read project memory."""
    content = _memory.project_memory.read()
    if not content:
        return "No DRAGUNITEUS.md found. Use /init to create one."
    return content