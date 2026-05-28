"""Layered configuration: env vars → settings file → defaults."""
from __future__ import annotations

import json
import os
import platform
from pathlib import Path
from typing import Any

import yaml


def _get_config_dir() -> Path:
    """User-level config directory (~/.draguniteus on Unix, %APPDATA%/draguniteus on Windows)."""
    if platform.system() == "Windows":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path.home()
    return base / ".draguniteus"


DEFAULT_CONFIG_DIR = _get_config_dir()
DEFAULT_SETTINGS_FILE = DEFAULT_CONFIG_DIR / "settings.json"
DEFAULT_SETTINGS_LOCAL = DEFAULT_CONFIG_DIR / "settings.local.json"
DEFAULT_CONFIG_FILE = DEFAULT_CONFIG_DIR / "config.json"  # Backward compat
DEFAULT_API_KEY_ENV = "ANTHROPIC_API_KEY"
DEFAULT_MODEL = "MiniMax-M2.7"
DEFAULT_BASE_URL = "https://api.minimax.io/anthropic"
DEFAULT_THEME = "full"  # "full" or "minimal"
DEFAULT_SESSION_MAX_TURNS = 50

# Effort levels map to actual API behaviors
EFFORT_LEVELS = {
    "low": {
        "max_tokens": 4096,
        "temperature": 0.7,
        "thinking": False,
        "betas": [],
    },
    "medium": {
        "max_tokens": 8192,
        "temperature": 1.0,
        "thinking": False,
        "betas": [],
    },
    "high": {
        "max_tokens": 8192,
        "temperature": 1.0,
        "thinking": True,
        "betas": [],
    },
    "xhigh": {
        "max_tokens": 16384,
        "temperature": 1.0,
        "thinking": True,
        "betas": ["interleaved-thinking"],
    },
    "max": {
        "max_tokens": 32768,
        "temperature": 1.0,
        "thinking": True,
        "betas": ["interleaved-thinking", "extended-thinking"],
    },
}


MINIMAX_MODELS = [
    "MiniMax-M2.7",   # 200k context, complex reasoning, recursive self-improvement
    "MiniMax-M2.5",  # Code generation and refactoring
    "MiniMax-M2.1",  # Code generation/refactoring, enhanced reasoning
    "MiniMax-M2",    # 200k context, agentic capabilities, function calling
]


class Config:
    """Layered config: env vars override file, file overrides defaults.

    Supports both settings.json (new) and config.json (legacy).
    Also supports settings.local.json for project-level overrides.
    """

    def __init__(self, config_file: Path | None = None, cli_overrides: dict[str, Any] | None = None):
        # Determine which config file to use
        if config_file:
            self.config_file = config_file
        else:
            # Prefer settings.json, fall back to config.json
            if DEFAULT_SETTINGS_FILE.exists():
                self.config_file = DEFAULT_SETTINGS_FILE
            else:
                self.config_file = DEFAULT_CONFIG_FILE

        self.config_dir = DEFAULT_CONFIG_DIR
        self._raw: dict[str, Any] = {}
        self._load()

        # Load project-level overrides (settings.local.json)
        self._load_local_overrides()

        # CLI overrides take highest priority
        if cli_overrides:
            self._raw.update(cli_overrides)

    def _load(self) -> None:
        """Load config from file if it exists."""
        # Migrate config.json -> settings.json if needed
        if DEFAULT_CONFIG_FILE.exists() and not DEFAULT_SETTINGS_FILE.exists():
            self.migrate_to_settings_json()

        if self.config_file.exists():
            with open(self.config_file, "r", encoding="utf-8") as f:
                self._raw = json.load(f)
        else:
            self._raw = {}

        # Handle 'env' field — values in env override top-level keys
        env_section = self._raw.get("env", {})
        if env_section:
            # Apply env values to _raw (except env itself)
            for key, value in env_section.items():
                if key == "ANTHROPIC_AUTH_TOKEN" and value:
                    # Alias for api_key
                    self._raw["api_key"] = value
                elif key == "ANTHROPIC_BASE_URL" and value:
                    self._raw["base_url"] = value
                elif key == "API_TIMEOUT_MS" and value:
                    self._raw["timeout_ms"] = int(value)
                else:
                    # Store env var names for reference
                    pass

    def _load_local_overrides(self) -> None:
        """Load project-level settings.local.json if it exists."""
        if DEFAULT_SETTINGS_LOCAL.exists():
            try:
                local_raw = json.loads(DEFAULT_SETTINGS_LOCAL.read_text(encoding="utf-8"))
                # Merge local overrides (higher priority than file)
                self._raw.update(local_raw)
            except Exception:
                pass

    @property
    def api_key(self) -> str:
        # Check env field first (ANTHROPIC_AUTH_TOKEN maps to api_key)
        env_token = os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
        if env_token:
            return env_token
        # Check ANTHROPIC_API_KEY env var
        api_key_env = self._raw.get("api_key_env", DEFAULT_API_KEY_ENV)
        return os.environ.get(api_key_env, self._raw.get("api_key", ""))

    @property
    def base_url(self) -> str:
        return os.environ.get("ANTHROPIC_BASE_URL", self._raw.get("base_url", DEFAULT_BASE_URL))

    @property
    def model(self) -> str:
        return self._raw.get("model", DEFAULT_MODEL)

    @property
    def theme(self) -> str:
        return self._raw.get("theme", DEFAULT_THEME)

    @property
    def max_tokens(self) -> int:
        return self._raw.get("max_tokens", 8192)

    @property
    def temperature(self) -> float:
        return self._raw.get("temperature", 1.0)

    @property
    def session_max_turns(self) -> int:
        return self._raw.get("session_max_turns", DEFAULT_SESSION_MAX_TURNS)

    @property
    def session_dir(self) -> Path:
        return self._raw.get("session_dir", DEFAULT_CONFIG_DIR / "sessions")

    @property
    def permissions_file(self) -> Path:
        return self._raw.get("permissions_file", DEFAULT_CONFIG_DIR / "permissions.json")

    @property
    def timeout_ms(self) -> int:
        return self._raw.get("timeout_ms", 300000)

    @property
    def mcp_servers(self) -> dict[str, Any]:
        """MCP server configurations (both mcpServers and mcp_servers keys accepted)."""
        servers = self._raw.get("mcpServers", {})
        if not servers:
            servers = self._raw.get("mcp_servers", {})
        return servers

    @property
    def tavily_api_key(self) -> str:
        """Tavily API key for web search."""
        return os.environ.get("TAVILY_API_KEY", self._raw.get("tavily_api_key", ""))

    @property
    def hooks(self) -> dict[str, Any]:
        """Get hook configurations from settings."""
        return self._raw.get("hooks", {})

    # -------------------------------------------------------------------------
    # Effort level
    # -------------------------------------------------------------------------

    @property
    def effort(self) -> str:
        return self._raw.get("effort", "medium")

    def get_effort_settings(self) -> dict[str, Any]:
        """Get full settings for current effort level."""
        level = self.effort
        return EFFORT_LEVELS.get(level, EFFORT_LEVELS["medium"])

    def set_effort(self, level: str) -> bool:
        """Set effort level. Returns True if valid level was set."""
        if level not in EFFORT_LEVELS:
            return False
        self._raw["effort"] = level
        return True

    # -------------------------------------------------------------------------
    # Persistence
    # -------------------------------------------------------------------------

    def save(self) -> None:
        """Write current config to file."""
        DEFAULT_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(self._raw, f, indent=2)

    @classmethod
    def first_launch(cls) -> bool:
        """Return True if this is the first launch (no config file exists)."""
        return not DEFAULT_SETTINGS_FILE.exists() and not DEFAULT_CONFIG_FILE.exists()

    def prompt_and_save_api_key(self, api_key: str) -> None:
        """Save API key to config file."""
        self._raw["api_key"] = api_key
        self.save()

    # -------------------------------------------------------------------------
    # Tool: load permissions
    # -------------------------------------------------------------------------

    def load_permissions(self) -> list[dict[str, Any]]:
        """Load permission rules from permissions.json if it exists."""
        pf = self.permissions_file
        if pf.exists():
            with open(pf, "r", encoding="utf-8") as f:
                return json.load(f)
        return []

    # -------------------------------------------------------------------------
    # Project-level config (`.draguniteus/` in cwd)
    # -------------------------------------------------------------------------

    @staticmethod
    def project_dir() -> Path:
        return Path.cwd() / ".draguniteus"

    @staticmethod
    def project_config() -> Path | None:
        pd = Config.project_dir()
        conf = pd / "settings.json"
        if conf.exists():
            return conf
        conf = pd / "config.json"
        return conf if conf.exists() else None

    @classmethod
    def load_project_overrides(cls) -> dict[str, Any]:
        """Load project-level overrides from .draguniteus/settings.json or .draguniteus/config.json."""
        path = cls.project_config()
        if not path:
            return {}
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    # -------------------------------------------------------------------------
    # Style support
    # -------------------------------------------------------------------------

    def get_style(self) -> str | None:
        """Get the active output style."""
        return self._raw.get("style")

    # -------------------------------------------------------------------------
    # Agent intelligence features
    # -------------------------------------------------------------------------

    @property
    def thinking_router_enabled(self) -> bool:
        return self._raw.get("thinking_router_enabled", True)

    @property
    def developer_role_enabled(self) -> bool:
        return self._raw.get("developer_role_enabled", True)

    @property
    def checkpoint_every(self) -> int:
        return self._raw.get("checkpoint_every", 5)

    @property
    def nested_tool_max_depth(self) -> int:
        return self._raw.get("nested_tool_max_depth", 5)

    @property
    def nested_tool_enabled(self) -> bool:
        return self._raw.get("nested_tool_enabled", True)

    @property
    def self_improvement_enabled(self) -> bool:
        return self._raw.get("self_improvement_enabled", True)

    @property
    def preview_server_enabled(self) -> bool:
        return self._raw.get("preview_server_enabled", False)

    @property
    def chromadb_enabled(self) -> bool:
        return self._raw.get("chromadb_enabled", True)

    @property
    def git_auto_commit_enabled(self) -> bool:
        return self._raw.get("git_auto_commit_enabled", False)

    # -------------------------------------------------------------------------
    # Migration helpers
    # -------------------------------------------------------------------------

    @classmethod
    def migrate_to_settings_json(cls) -> None:
        """Migrate config.json to settings.json if needed."""
        if DEFAULT_CONFIG_FILE.exists() and not DEFAULT_SETTINGS_FILE.exists():
            try:
                data = json.loads(DEFAULT_CONFIG_FILE.read_text(encoding="utf-8"))
                DEFAULT_SETTINGS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
            except Exception:
                pass