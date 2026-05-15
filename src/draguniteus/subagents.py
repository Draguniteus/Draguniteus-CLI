"""Sub-agents: built-in agents + custom agent loading via AgentLoader."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

BUILTIN_AGENTS: dict[str, dict[str, Any]] = {
    "explore": {
        "name": "Explore",
        "description": "Deep search of codebase — finds patterns, maps structure",
        "system_prompt": "You are Explore, a dragon-eyed code scout. Search thoroughly, report findings with precision.",
        "model": "MiniMax-M2.7",
        "tools": ["Read", "Glob", "Grep"],
    },
    "plan": {
        "name": "Plan",
        "description": "Architectural planning and strategy",
        "system_prompt": "You are Plan, the ancient dragon strategist. Think several steps ahead. Create clear, actionable plans.",
        "model": "MiniMax-M2.7",
        "tools": ["Read", "Glob", "Grep", "Bash"],
    },
    "review": {
        "name": "Review",
        "description": "Code review with improvement suggestions",
        "system_prompt": "You are Review, a meticulous dragon auditor. Examine code carefully, suggest improvements.",
        "model": "MiniMax-M2.7",
        "tools": ["Read", "Bash", "GitDiff"],
    },
    "debug": {
        "name": "Debug",
        "description": "Systematic debugging and fix execution",
        "system_prompt": "You are Debug, the draconic troubleshooter. Find root causes, fix methodically, verify your fixes.",
        "model": "MiniMax-M2.7",
        "tools": ["Read", "Bash", "Grep", "Edit"],
    },
}


def load_agent(name: str) -> dict[str, Any] | None:
    """Load a built-in or custom agent definition.

    Checks in order:
    1. Built-in agents (explore, plan, review, debug)
    2. Plugin agents via AgentLoader (after discovering plugins)
    3. Local agents/ directory (JSON files)
    """
    # Check built-in first
    if name.lower() in BUILTIN_AGENTS:
        return BUILTIN_AGENTS[name.lower()]

    # Check AgentLoader (plugin agents) - must discover plugins first
    try:
        from draguniteus.agents.loader import get_agent_loader
        from draguniteus.plugins.manager import get_plugin_manager

        loader = get_agent_loader()
        plugin_mgr = get_plugin_manager()

        # Load agents from discovered plugins
        plugins = plugin_mgr.discover_plugins()
        for plugin in plugins:
            if plugin.manifest.agents_dir.exists():
                loader.load_directory(plugin.manifest.agents_dir)

        # Also try default plugin directories
        plugin_dirs = [
            Path.home() / ".draguniteus" / "plugins",
            Path.cwd() / ".draguniteus" / "plugins",
        ]
        for plugin_dir in plugin_dirs:
            if plugin_dir.exists():
                for plugin_path in plugin_dir.iterdir():
                    if plugin_path.is_dir():
                        agents_dir = plugin_path / "agents"
                        if agents_dir.exists():
                            loader.load_directory(agents_dir)

        agent_def = loader.get_agent(name.lower())
        if agent_def:
            return {
                "name": agent_def.name,
                "description": agent_def.description,
                "system_prompt": agent_def.body,
                "model": agent_def.model,
                "tools": agent_def.tools,
            }
    except Exception:
        pass

    # Check local agents/ directory for JSON files
    agents_dir = Path(__file__).parent.parent.parent / "agents"
    agent_file = agents_dir / f"{name}.json"
    if agent_file.exists():
        with open(agent_file, "r", encoding="utf-8") as f:
            return json.load(f)

    return None


def list_agents() -> list[dict[str, str]]:
    """Return all available agents as a list of {name, description}."""
    result = []
    for key, agent in BUILTIN_AGENTS.items():
        result.append({"name": agent["name"], "description": agent["description"]})

    # Add plugin agents from AgentLoader
    try:
        from draguniteus.agents.loader import get_agent_loader
        from draguniteus.plugins.manager import get_plugin_manager

        loader = get_agent_loader()
        plugin_mgr = get_plugin_manager()

        # Load agents from discovered plugins
        plugins = plugin_mgr.discover_plugins()
        for plugin in plugins:
            if plugin.manifest.agents_dir.exists():
                loader.load_directory(plugin.manifest.agents_dir)

        # Also try default plugin directories
        plugin_dirs = [
            Path.home() / ".draguniteus" / "plugins",
            Path.cwd() / ".draguniteus" / "plugins",
        ]
        for plugin_dir in plugin_dirs:
            if plugin_dir.exists():
                for plugin_path in plugin_dir.iterdir():
                    if plugin_path.is_dir():
                        agents_dir = plugin_path / "agents"
                        if agents_dir.exists():
                            loader.load_directory(agents_dir)

        for agent_def in loader.list_agents():
            # Avoid duplicates with builtins
            if not any(a["name"] == agent_def.name for a in result):
                result.append({"name": agent_def.name, "description": agent_def.description})
    except Exception:
        pass

    return result


def route_query_to_agent(query: str) -> dict[str, Any] | None:
    """Route a user query to the best-matching agent using match_score().

    Returns agent definition dict if match_score >= 0.3, else None.
    This enables natural language agent selection.
    """
    from draguniteus.agents.loader import get_agent_loader, AgentDefinition
    from draguniteus.plugins.manager import get_plugin_manager

    loader = get_agent_loader()
    plugin_mgr = get_plugin_manager()

    # Load agents from discovered plugins (same as list_agents)
    plugins = plugin_mgr.discover_plugins()
    for plugin in plugins:
        if plugin.manifest.agents_dir.exists():
            loader.load_directory(plugin.manifest.agents_dir)

    # Also try default plugin directories
    plugin_dirs = [
        Path.home() / ".draguniteus" / "plugins",
        Path.cwd() / ".draguniteus" / "plugins",
    ]
    for plugin_dir in plugin_dirs:
        if plugin_dir.exists():
            for plugin_path in plugin_dir.iterdir():
                if plugin_path.is_dir():
                    agents_dir = plugin_path / "agents"
                    if agents_dir.exists():
                        loader.load_directory(agents_dir)

    # Build a list of all agents (plugin + built-in) with match_score
    all_candidates: list[tuple[AgentDefinition | dict, float]] = []

    # Plugin agents (AgentDefinition objects)
    for agent_def in loader.list_agents():
        score = agent_def.match_score(query)
        all_candidates.append((agent_def, score))

    # Built-in agents (dict objects) - convert to AgentDefinition-like scoring
    for key, builtin in BUILTIN_AGENTS.items():
        desc = builtin.get("description", "")
        body = builtin.get("system_prompt", "")
        query_lower = query.lower()
        desc_lower = desc.lower()

        # Simple keyword overlap scoring
        import re
        score = 0.0
        query_words = set(query_lower.split())
        desc_words = set(desc_lower.split())
        overlap = query_words & desc_words
        if query_words:
            score += len(overlap) / len(query_words) * 0.4

        # Agent key as trigger (e.g. "explore" query triggers "explore" agent)
        key_trigger = 0.3 if key in query_lower else 0.0

        # Trigger phrase detection (if phrase appears in query - describes when to use)
        trigger_phrases = ["explore", "plan", "review", "debug", "search", "map", "find", "audit", "fix"]
        trigger_score = 0.0
        for phrase in trigger_phrases:
            if phrase in query_lower:
                trigger_score = 0.2
                break

        all_candidates.append((builtin, score + key_trigger + trigger_score))

    # Find best match
    best_candidate = None
    best_score = 0.0

    for candidate, score in all_candidates:
        if score > best_score:
            best_score = score
            best_candidate = candidate

    if best_score >= 0.3 and best_candidate:
        if isinstance(best_candidate, dict):
            # Built-in agent dict
            return {
                "name": best_candidate["name"],
                "description": best_candidate["description"],
                "system_prompt": best_candidate["system_prompt"],
                "model": best_candidate.get("model", "inherit"),
                "tools": best_candidate.get("tools"),
                "match_score": best_score,
            }
        else:
            # AgentDefinition object
            return {
                "name": best_candidate.name,
                "description": best_candidate.description,
                "system_prompt": best_candidate.body,
                "model": best_candidate.model,
                "tools": best_candidate.tools,
                "match_score": best_score,
            }
    return None