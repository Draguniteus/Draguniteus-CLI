"""Output style management system."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from draguniteus.config import Config


class Style:
    """A loaded output style."""

    def __init__(self, name: str, description: str, content: str, path: Path):
        self.name = name
        self.description = description
        self.content = content
        self.path = path

    def apply(self, system_prompt: str) -> str:
        """Apply this style to a system prompt."""
        return f"{system_prompt}\n\n{self.content}"

    def __repr__(self) -> str:
        return f"Style({self.name})"


class StyleManager:
    """Manages output styles from ~/.draguniteus/styles/."""

    def __init__(self, config: Config | None = None):
        self.config = config or Config()
        self.styles_dir = self.config.config_dir / "styles"
        self._styles: dict[str, Style] = {}
        self._discover_styles()
        # Auto-create defaults if no styles exist
        if not self._styles:
            self.create_default_styles()

    def _discover_styles(self) -> None:
        """Discover and load all style files."""
        if not self.styles_dir.exists():
            return

        for path in self.styles_dir.glob("*.md"):
            style = self._load_style(path)
            if style:
                self._styles[style.name] = style

    def _load_style(self, path: Path) -> Style | None:
        """Load a single style file."""
        try:
            content = path.read_text(encoding="utf-8")
        except Exception:
            return None

        name = path.stem
        description = ""
        body = content

        # Parse YAML frontmatter
        match = re.match(r"^---\n(.*?)\n---\n", content, re.DOTALL)
        if match:
            frontmatter = match.group(1)
            name = self._parse_field(frontmatter, "name", name)
            description = self._parse_field(frontmatter, "description", "")
            body = content[match.end():]

        return Style(name, description, body.strip(), path)

    def _parse_field(self, text: str, field: str, default: str = "") -> str:
        """Extract a field value from frontmatter text."""
        for line in text.split("\n"):
            if line.startswith(f"{field}:"):
                val = line.split(":", 1)[1].strip()
                if val.startswith('"') and val.endswith('"'):
                    return val[1:-1]
                if val.startswith("'") and val.endswith("'"):
                    return val[1:-1]
                return val
        return default

    def get_style(self, name: str) -> Style | None:
        """Get a style by name."""
        return self._styles.get(name)

    def list_styles(self) -> list[Style]:
        """List all available styles."""
        return list(self._styles.values())

    def apply_style(self, name: str, system_prompt: str) -> str:
        """Apply a named style to a system prompt."""
        style = self._styles.get(name)
        if not style:
            return system_prompt
        return style.apply(system_prompt)

    def create_default_styles(self) -> None:
        """Create default style files if none exist."""
        if self._styles:
            return  # Already have styles

        self.styles_dir.mkdir(parents=True, exist_ok=True)

        explanatory = """---
name: explanatory
description: Explanatory output style for learning
---

## Output Style: Explanatory

When responding, follow these guidelines:

- Explain what the code does, not just what to change
- Use analogies and concrete examples to illustrate concepts
- Break down complex problems into step-by-step explanations
- Show your reasoning and tradeoffs considered
- Include relevant context from the codebase
- Prefer readable, well-commented code over clever one-liners
- When suggesting changes, explain why they improve the code
"""
        (self.styles_dir / "explanatory.md").write_text(explanatory, encoding="utf-8")

        learning = """---
name: learning
description: Learning-focused output with detailed explanations
---

## Output Style: Learning

When responding, follow these guidelines:

- Teach concepts before giving solutions
- Start with the big picture, then dive into details
- Use analogies to connect new concepts to things the user already knows
- Anticipate follow-up questions and address them proactively
- Provide historical context for why things are designed certain ways
- Show multiple approaches with their tradeoffs
- Include "fun fact" annotations for interesting edge cases
- Mark advanced topics with "🔒 Advanced" markers for optional depth
"""
        (self.styles_dir / "learning.md").write_text(learning, encoding="utf-8")

        # Reload
        self._styles.clear()
        self._discover_styles()


# Global style manager
_style_manager: StyleManager | None = None


def get_style_manager() -> StyleManager:
    global _style_manager
    if _style_manager is None:
        _style_manager = StyleManager()
    return _style_manager