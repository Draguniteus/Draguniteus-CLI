"""Plugin management system for Draguniteus."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from draguniteus.config import Config

from draguniteus.plugins.settings import PluginSettings


class PluginManifest:
    """Parsed plugin.json manifest."""

    def __init__(self, path: Path, data: dict[str, Any]):
        self.path = path
        self.name = data.get("name", "")
        self.version = data.get("version", "0.1.0")
        self.description = data.get("description", "")
        self.author = data.get("author", {})
        self.homepage = data.get("homepage", "")
        self.repository = data.get("repository", "")
        self.license = data.get("license", "MIT")
        self.keywords = data.get("keywords", [])

    @property
    def root(self) -> Path:
        return self.path.parent.parent

    @property
    def commands_dir(self) -> Path:
        return self.root / "commands"

    @property
    def agents_dir(self) -> Path:
        return self.root / "agents"

    @property
    def hooks_file(self) -> Path:
        return self.root / "hooks" / "hooks.json"

    @property
    def mcp_file(self) -> Path:
        return self.root / ".mcp.json"


class Plugin:
    """Loaded plugin instance."""

    def __init__(self, manifest: PluginManifest):
        self.manifest = manifest
        self.name = manifest.name
        self.settings = PluginSettings(manifest.name)
        self._commands: dict[str, Path] = {}
        self._agents: dict[str, Path] = {}
        self._skills: list[Path] = []
        self._mcp_servers: dict[str, dict] = {}
        self._hooks_config: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        """Load plugin components."""
        self._load_commands()
        self._load_agents()
        self._load_skills()
        self._load_mcp()
        self._load_hooks()

    def _load_commands(self) -> None:
        """Discover command files."""
        if not self.manifest.commands_dir.exists():
            return
        for f in self.manifest.commands_dir.glob("*.md"):
            cmd_name = f.stem.replace("_", "-")
            self._commands[cmd_name] = f

    def _load_agents(self) -> None:
        """Discover agent files."""
        if not self.manifest.agents_dir.exists():
            return
        for f in self.manifest.agents_dir.glob("*.md"):
            agent_name = f.stem.replace("_", "-")
            self._agents[agent_name] = f

    def _load_skills(self) -> None:
        """Discover skill directories."""
        skills_dir = self.manifest.root / "skills"
        if not skills_dir.exists():
            return
        for item in skills_dir.iterdir():
            if item.is_dir() and (item / "SKILL.md").exists():
                self._skills.append(item)

    def _load_mcp(self) -> None:
        """Load MCP server configuration."""
        if not self.manifest.mcp_file.exists():
            return
        try:
            content = self.manifest.mcp_file.read_text(encoding="utf-8")
            # Expand ${CLAUDE_PLUGIN_ROOT}
            content = content.replace(
                "${CLAUDE_PLUGIN_ROOT}",
                str(self.manifest.root)
            )
            data = json.loads(content)
            self._mcp_servers = data.get("mcpServers", {})
        except Exception:
            pass

    def _load_hooks(self) -> None:
        """Load hooks.json configuration."""
        if not self.manifest.hooks_file.exists():
            return
        try:
            self._hooks_config = json.loads(
                self.manifest.hooks_file.read_text(encoding="utf-8")
            )
        except Exception:
            pass

    @property
    def commands(self) -> dict[str, Path]:
        return self._commands

    @property
    def agents(self) -> dict[str, Path]:
        return self._agents

    @property
    def skills(self) -> list[Path]:
        return self._skills

    @property
    def mcp_servers(self) -> dict[str, dict]:
        return self._mcp_servers

    @property
    def hooks(self) -> dict[str, Any]:
        return self._hooks_config.get("hooks", {})

    def get_command(self, name: str) -> Path | None:
        return self._commands.get(name)

    def get_agent(self, name: str) -> Path | None:
        return self._agents.get(name)


class PluginManager:
    """Manages plugin discovery, loading, and lifecycle."""

    def __init__(self, config: Config | None = None):
        self.config = config or Config()
        self._plugins: dict[str, Plugin] = {}
        self._mcp_client: Any = None  # Set by set_mcp_client()

    def set_mcp_client(self, mcp_client: Any) -> None:
        """Set the MCP client for starting servers."""
        self._mcp_client = mcp_client

    def discover_plugins(self) -> list[Plugin]:
        """Discover and load all plugins from standard locations."""
        plugin_dirs: list[Path] = []

        # User-level plugins
        user_plugins = self.config.config_dir / "plugins"
        if user_plugins.exists():
            plugin_dirs.extend(p for p in user_plugins.iterdir() if p.is_dir())

        # Project-level plugins
        project_plugins = self.config.project_dir() / "plugins"
        if project_plugins.exists():
            plugin_dirs.extend(p for p in project_plugins.iterdir() if p.is_dir())

        # Deduplicate by name
        seen: set[str] = set()
        for d in plugin_dirs:
            manifest_path = d / ".draguniteus-plugin" / "plugin.json"
            if manifest_path.exists() and d.name not in seen:
                seen.add(d.name)
                try:
                    data = json.loads(manifest_path.read_text(encoding="utf-8"))
                    manifest = PluginManifest(manifest_path, data)
                    plugin = Plugin(manifest)
                    self._plugins[plugin.name] = plugin
                    self._start_mcp_servers(plugin)
                except Exception:
                    pass

        return list(self._plugins.values())

    def _start_mcp_servers(self, plugin: Plugin) -> None:
        """Start MCP servers defined in plugin's .mcp.json."""
        if not self._mcp_client or not plugin.mcp_servers:
            return

        for server_name, server_config in plugin.mcp_servers.items():
            try:
                self._mcp_client.add_server(
                    name=f"plugin_{plugin.name}_{server_name}",
                    command=server_config.get("command", ""),
                    args=server_config.get("args", []),
                    env=server_config.get("env", {}),
                    server_type=server_config.get("type", "stdio"),
                    url=server_config.get("url"),
                )
            except Exception:
                pass

    def get_plugin(self, name: str) -> Plugin | None:
        """Get a loaded plugin by name."""
        return self._plugins.get(name)

    def list_plugins(self) -> list[str]:
        """List all loaded plugin names."""
        return list(self._plugins.keys())

    def get_all_commands(self) -> dict[str, Path]:
        """Get all commands from all plugins."""
        result = {}
        for plugin in self._plugins.values():
            result.update(plugin.commands)
        return result

    def get_all_agents(self) -> dict[str, Path]:
        """Get all agents from all plugins."""
        result = {}
        for plugin in self._plugins.values():
            result.update(plugin.agents)
        return result

    def get_all_hooks(self) -> dict[str, list[dict]]:
        """Get all hooks from all plugins, keyed by event name."""
        result: dict[str, list[dict]] = {}
        for plugin in self._plugins.values():
            for event_name, hooks in plugin.hooks.items():
                if event_name not in result:
                    result[event_name] = []
                result[event_name].extend(hooks)
        return result


# Global plugin manager instance
_plugin_manager: PluginManager | None = None


def get_plugin_manager() -> PluginManager:
    global _plugin_manager
    if _plugin_manager is None:
        _plugin_manager = PluginManager()
    return _plugin_manager


def discover_all_plugins() -> list[Plugin]:
    """Convenience function to discover and load all plugins."""
    manager = get_plugin_manager()
    return manager.discover_plugins()