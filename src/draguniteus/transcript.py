"""Transcript viewer: interactive viewer for session transcripts with Ctrl+O."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from draguniteus.session import Session


class TranscriptViewer:
    """Interactive transcript viewer with expand/collapse and search."""

    def __init__(self):
        self.current_session: Session | None = None

    def view_session(self, session: Session, events: list[dict[str, Any]]) -> None:
        """Display the transcript in a viewer."""
        if not events:
            print("[D] No transcript to display.")
            return

        # Build transcript content
        lines = ["=" * 60, " DRAGUNITEUS TRANSCRIPT VIEWER ", "=" * 60, ""]

        for i, event in enumerate(events):
            etype = event.get("type", "unknown")
            content = event.get("content", "")

            if etype == "user":
                lines.append(f"[USER] {content[:100]}")
            elif etype == "assistant":
                # Truncate long responses
                if len(content) > 200:
                    content = content[:200] + "..."
                lines.append(f"[DRAGON] {content[:100]}")
            elif etype == "shell":
                lines.append(f"[SHELL] {event.get('content', '')}")
            elif etype == "tool":
                tool_name = event.get("tool", "?")
                result = event.get("result", "")
                if len(result) > 100:
                    result = result[:100] + "..."
                lines.append(f"[TOOL: {tool_name}] {result}")

            if i < len(events) - 1:
                lines.append("-" * 40)

        lines.append("=" * 60)
        lines.append(f"End of transcript ({len(events)} events)")
        lines.append("=" * 60)
        lines.append("Shortcuts: Ctrl+E toggle | v write to $VISUAL | q/Esc exit")

        # Write to temp file and open in editor
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
            temp_file = f.name
            f.write("\n".join(lines))

        # Open in visual editor
        visual = subprocess.environ.get("VISUAL") or subprocess.environ.get("EDITOR") or "less"
        try:
            if visual == "less":
                subprocess.run(["less", str(temp_file)], check=False)
            else:
                subprocess.run([visual, str(temp_file)], check=False)
        except Exception:
            # Fallback: just print to stdout
            for line in lines:
                print(line)

    def view_compact(self, session: Session, events: list[dict[str, Any]]) -> str:
        """Return a compact summary of the transcript."""
        if not events:
            return "Empty transcript"

        tool_counts: dict[str, int] = {}
        user_messages = 0
        assistant_messages = 0

        for event in events:
            etype = event.get("type", "unknown")
            if etype == "user":
                user_messages += 1
            elif etype == "assistant":
                assistant_messages += 1
            elif etype == "tool":
                tool = event.get("tool", "unknown")
                tool_counts[tool] = tool_counts.get(tool, 0) + 1

        parts = [f"User messages: {user_messages}", f"Assistant messages: {assistant_messages}"]
        if tool_counts:
            tools_str = ", ".join(f"{k}({v})" for k, v in tool_counts.items())
            parts.append(f"Tools used: {tools_str}")

        return " | ".join(parts)

    def write_to_scrollback(self, events: list[dict[str, Any]]) -> str:
        """Format transcript for writing to terminal scrollback."""
        lines = []
        for event in events:
            etype = event.get("type", "unknown")
            if etype == "user":
                lines.append(f"[USER] {event.get('content', '')}")
            elif etype == "assistant":
                lines.append(f"[DRAGON] {event.get('content', '')}")
            elif etype == "shell":
                lines.append(f"[SHELL] {event.get('content', '')}")
        return "\n".join(lines)


# Global instance
transcript_viewer = TranscriptViewer()