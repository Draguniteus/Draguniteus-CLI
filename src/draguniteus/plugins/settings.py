"""Plugin settings reader for .draguniteus/<plugin-name>.local.md files."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from draguniteus.config import Config


class PluginSettings:
    """Reads and parses plugin .local.md settings files."""

    def __init__(self, plugin_name: str):
        self.plugin_name = plugin_name
        self._data: dict[str, Any] = {}
        self._body: str = ""
        self._load()

    def _load(self) -> None:
        config = Config()
        settings_path = config.project_dir() / f"{self.plugin_name}.local.md"
        if not settings_path.exists():
            return

        try:
            content = settings_path.read_text(encoding="utf-8")
        except Exception:
            return

        # Parse YAML frontmatter
        match = re.match(r"^---\n(.*?)\n---(?:\n)?", content, re.DOTALL)
        if match:
            frontmatter = match.group(1)
            self._data = self._parse_frontmatter(frontmatter)
            self._body = content[match.end():]
        else:
            self._body = content

    def _parse_frontmatter(self, text: str) -> dict[str, Any]:
        """Parse YAML frontmatter into a dict."""
        result: dict[str, Any] = {}
        for line in text.split("\n"):
            if ":" in line:
                key, val = line.split(":", 1)
                key = key.strip()
                val = val.strip()
                if val.startswith("[") and val.endswith("]"):
                    # List value
                    items = [s.strip().strip('"').strip("'") for s in val[1:-1].split(",")]
                    result[key] = items
                elif val.startswith("{") and val.endswith("}"):
                    # Dict value - store as JSON string for now
                    result[key] = val
                elif val == "true":
                    result[key] = True
                elif val == "false":
                    result[key] = False
                elif val.startswith('"') and val.endswith('"'):
                    result[key] = val[1:-1]
                elif val.startswith("'") and val.endswith("'"):
                    result[key] = val[1:-1]
                else:
                    # Try numeric
                    try:
                        result[key] = int(val)
                    except ValueError:
                        result[key] = val
        return result

    def get(self, key: str, default: Any = None) -> Any:
        """Get a setting value."""
        return self._data.get(key, default)

    def is_enabled(self) -> bool:
        """Check if plugin is enabled (defaults to True)."""
        return self._data.get("enabled", True)

    @property
    def body(self) -> str:
        """Return markdown body after frontmatter."""
        return self._body

    def __repr__(self) -> str:
        return f"PluginSettings({self.plugin_name}, enabled={self.is_enabled()}, {len(self._data)} settings)"