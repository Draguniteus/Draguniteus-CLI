"""Skills loader: Markdown-based skills with YAML frontmatter."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml


class Skill:
    def __init__(self, name: str, description: str, content: str, metadata: dict[str, Any]):
        self.name = name
        self.description = description
        self.content = content
        self.metadata = metadata


def load_skill(path: Path) -> Skill | None:
    """Load a skill from a directory containing SKILL.md."""
    skill_md = path / "SKILL.md"
    if not skill_md.exists():
        return None

    content = skill_md.read_text(encoding="utf-8")

    # Parse YAML frontmatter
    frontmatter_match = re.match(r"^---\n(.*?)\n---\n(.*)", content, re.DOTALL)
    if not frontmatter_match:
        return None

    try:
        metadata = yaml.safe_load(frontmatter_match.group(1))
        body = frontmatter_match.group(2)
    except Exception:
        return None

    name = metadata.get("name", path.name)
    description = metadata.get("description", "")

    return Skill(name=name, description=description, content=body, metadata=metadata)


def load_all_skills(skills_dir: Path | None = None) -> list[Skill]:
    """Load all skills from the skills directory."""
    if skills_dir is None:
        # Check multiple locations: project .draguniteus/skills, user home .draguniteus/skills, src/skills
        import os
        cwd = Path.cwd()
        locations = [
            cwd / ".draguniteus" / "skills",
            cwd / "skills",
            Path.home() / ".draguniteus" / "skills",
            Path(__file__).parent.parent.parent / ".draguniteus" / "skills",
        ]
        for loc in locations:
            if loc.exists():
                skills_dir = loc
                break
        if skills_dir is None:
            return []

    if not skills_dir.exists():
        return []

    skills = []
    # Walk the directory tree to find all SKILL.md files at any depth
    for entry in skills_dir.rglob("SKILL.md"):
        # entry is a SKILL.md file, parent is the skill directory
        skill_dir = entry.parent
        skill = load_skill(skill_dir)
        if skill:
            skills.append(skill)

    return skills


def load_skill_by_name(skill_name: str) -> Skill | None:
    """Find and load a skill by name across all known skill locations."""
    skills = load_all_skills()
    for skill in skills:
        if skill.name.lower() == skill_name.lower():
            return skill
    return None


def get_skill_tools() -> list[dict[str, Any]]:
    """Return skill tool definitions (for skills that define tools)."""
    skills = load_all_skills()
    tools = []
    for skill in skills:
        # Skills can define custom tools in their metadata
        if "tools" in skill.metadata:
            for t in skill.metadata["tools"]:
                tools.append(t)
    return tools


def execute_skill(skill: Skill, context: dict[str, Any]) -> dict[str, Any]:
    """Execute a skill's instructions with provided context.

    Args:
        skill: Loaded Skill object
        context: Execution context with keys:
            - query: str — the prompt/task for this skill
            - messages: list[dict] — optional, conversation history
            - session: Session — optional, session for config access

    Returns:
        {"output": str, "success": bool, "duration_ms": float}
    """
    import time

    start = time.time()
    query = context.get("query", "")
    messages = context.get("messages", [{"role": "user", "content": query}])

    try:
        from draguniteus.client import DraguniteusClient
        from draguniteus.agent import StreamHandler
        from draguniteus.config import Config

        config = Config()
        client = DraguniteusClient(config)

        # Build system prompt with skill content as directive
        system = skill.content.strip()
        if query:
            system = system + f"\n\nTask: {query}"

        # Execute via streaming agent loop
        stream = client.stream(
            messages=messages,
            tools=[],
            system=system,
        )
        handler = StreamHandler(None, False)

        for event in stream:
            handler.handle_event(event)

        output_text = handler.get_text()
        if not output_text:
            output_text = "[No response generated]"

        duration_ms = (time.time() - start) * 1000
        return {
            "output": output_text,
            "success": True,
            "duration_ms": round(duration_ms, 1),
        }
    except Exception as e:
        duration_ms = (time.time() - start) * 1000
        return {
            "output": f"Skill execution error: {e}",
            "success": False,
            "duration_ms": round(duration_ms, 1),
        }