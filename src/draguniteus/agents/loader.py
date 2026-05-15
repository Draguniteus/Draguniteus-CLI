"""Agent definition loader - supports .md files with YAML frontmatter."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any


class AgentDefinition:
    """Loaded agent definition from .md file."""

    def __init__(self, path: Path, frontmatter: dict[str, Any], body: str):
        self.path = path
        self.name = frontmatter.get("name", path.stem)
        self.description = frontmatter.get("description", "")
        self.model = frontmatter.get("model", "inherit")
        self.color = frontmatter.get("color", "green")
        self.tools = frontmatter.get("tools", None)  # None = full access
        self.body = body

    def match_score(self, query: str) -> float:
        """Calculate how well a query matches this agent definition. Returns 0.0-1.0."""
        import re
        score = 0.0
        query_lower = query.lower()
        desc_lower = self.description.lower()
        body_lower = self.body.lower()

        # Keyword overlap between query and description
        query_words = set(query_lower.split())
        desc_words = set(desc_lower.split())
        overlap = query_words & desc_words
        if query_words:
            score += len(overlap) / len(query_words) * 0.4

        # Example block matching
        example_sections = re.findall(r"<example>(.*?)</example>", self.body, re.DOTALL | re.IGNORECASE)
        for section in example_sections:
            if "user:" in section.lower() and query_lower in section.lower():
                score += 0.3
                break

        # Trigger phrase detection
        trigger_phrases = ["when the user", "if the user", "asks to", "wants to", "mentions"]
        for phrase in trigger_phrases:
            if phrase in desc_lower and phrase in query_lower:
                score += 0.2
                break

        # "use this agent" phrase match
        if "use this agent" in body_lower or "use this skill" in body_lower:
            if query_lower in body_lower:
                score += 0.1

        return min(score, 1.0)

    def matches_query(self, query: str) -> bool:
        """Check if query matches description patterns (legacy bool interface)."""
        return self.match_score(query) >= 0.3

    def __repr__(self) -> str:
        return f"Agent({self.name}, model={self.model}, color={self.color})"


class AgentLoader:
    """Loads agent definitions from .md files."""

    def __init__(self):
        self._agents: dict[str, AgentDefinition] = {}

    def load_agent(self, path: Path) -> AgentDefinition | None:
        """Load a single agent from a .md file."""
        try:
            content = path.read_text(encoding="utf-8")
        except Exception:
            return None

        # Parse YAML frontmatter
        match = re.match(r"^---\n(.*?)\n---\n", content, re.DOTALL)
        if not match:
            return None

        frontmatter_text = match.group(1)
        body = content[match.end():]

        frontmatter = self._parse_frontmatter(frontmatter_text)
        if not frontmatter.get("name"):
            return None

        agent = AgentDefinition(path, frontmatter, body)
        self._agents[agent.name] = agent
        return agent

    def _parse_frontmatter(self, text: str) -> dict[str, Any]:
        """Parse YAML frontmatter."""
        result: dict[str, Any] = {}
        lines = text.split("\n")
        i = 0
        while i < len(lines):
            line = lines[i]
            # Check for indented continuation
            if line.startswith(" ") or line.startswith("\t"):
                i += 1
                continue
            if ":" not in line:
                i += 1
                continue

            key, val = line.split(":", 1)
            key = key.strip()
            val = val.strip()

            if val in ("", "|"):
                # Multi-line value (block scalar)
                if val == "|" and i + 1 < len(lines):
                    i += 1
                    # Collect indented lines
                    lines_joined = []
                    while i < len(lines) and (lines[i].startswith("  ") or lines[i].startswith("\t") or lines[i].strip() == ""):
                        if lines[i].strip():
                            lines_joined.append(lines[i].strip())
                        i += 1
                    result[key] = "\n".join(lines_joined)
                    continue
                result[key] = ""
            elif val.startswith("[") and val.endswith("]"):
                # List value
                items = [s.strip().strip('"').strip("'") for s in val[1:-1].split(",")]
                result[key] = items
            elif val.startswith('"') and val.endswith('"'):
                result[key] = val[1:-1]
            elif val.startswith("'") and val.endswith("'"):
                result[key] = val[1:-1]
            elif val == "true":
                result[key] = True
            elif val == "false":
                result[key] = False
            else:
                try:
                    result[key] = int(val)
                except ValueError:
                    result[key] = val
            i += 1

        return result

    def load_directory(self, directory: Path) -> list[AgentDefinition]:
        """Load all agents from a directory."""
        agents = []
        if not directory.exists():
            return agents

        for path in directory.glob("*.md"):
            agent = self.load_agent(path)
            if agent:
                agents.append(agent)
        return agents

    def get_agent(self, name: str) -> AgentDefinition | None:
        """Get an agent by name."""
        return self._agents.get(name)

    def list_agents(self) -> list[AgentDefinition]:
        """List all loaded agents."""
        return list(self._agents.values())


# Global agent loader
_agent_loader: AgentLoader | None = None


def get_agent_loader() -> AgentLoader:
    global _agent_loader
    if _agent_loader is None:
        _agent_loader = AgentLoader()
    return _agent_loader