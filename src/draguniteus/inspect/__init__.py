"""Introspection: self-examination of Draguniteus's entire environment.

Exposes everything about the running instance for:
- /inspect command in CLI
- InspectEnvironment tool (so the agent can query itself)
- draguniteus info --json (machine-readable dump for web UI)
- draguniteus doctor (self-diagnosis)
"""
from __future__ import annotations

import json
import os
import platform
import sys
from pathlib import Path
from typing import Any

from draguniteus import __version__
from draguniteus.config import Config, DEFAULT_CONFIG_DIR


# ---------------------------------------------------------------------------
# Section collectors
# ---------------------------------------------------------------------------

def _collect_config() -> dict[str, Any]:
    cfg = Config()
    raw = dict(cfg._raw)
    # Redact sensitive values
    for key in ("api_key", "apiKey", "secret", "password", "token"):
        if key in raw and raw[key]:
            raw[key] = redacted(raw[key])
    settings = cfg.get_effort_settings()
    return {
        "config_file": str(cfg.config_file),
        "config_dir": str(cfg.config_dir),
        "model": cfg.model,
        "effort": cfg.effort,
        "max_tokens": cfg.max_tokens,
        "temperature": cfg.temperature,
        "thinking": settings["thinking"],
        "betas": settings["betas"],
        "base_url": cfg.base_url,
        "api_key_set": bool(cfg.api_key),
        "api_key_prefix": cfg.api_key[:8] + "..." if cfg.api_key else None,
        "raw_keys": list(raw.keys()),
    }


def _collect_env() -> dict[str, str]:
    """Collect relevant env vars, redacted."""
    vars = {}
    for key in ("ANTHROPIC_API_KEY", "MINIMAX_API_KEY", "OPENAI_API_KEY",
                "PATH", "HOME", "USER", "USERNAME",
                "DRAGUNITEUS_CONFIG", "DRAGUNITEUS_SESSION",
                "CLAUDE_APP_DIR", "XDG_CONFIG_HOME"):
        val = os.environ.get(key, "")
        if val:
            if "KEY" in key or "SECRET" in key or "TOKEN" in key:
                val = redacted(val)
            elif key == "PATH":
                val = ":".join(val.split(":")[:5]) + ":..."
            vars[key] = val
    return vars


def _collect_session() -> dict[str, Any]:
    from draguniteus.session import SessionStore
    try:
        store = SessionStore()
        sessions = list(store._sessions.keys())[-5:]
        return {
            "sessions_available": len(store._sessions),
            "recent_session_ids": sessions,
        }
    except Exception:
        return {"error": "session store unavailable"}


def _collect_tools() -> dict[str, Any]:
    from draguniteus.tools import ALL_TOOLS, TOOL_MAP
    return {
        "total_tools": len(ALL_TOOLS),
        "tool_names": sorted(t.get("name", "?") for t in ALL_TOOLS),
        "has_mcp_tools": False,  # Updated if MCP is loaded
    }


def _collect_git() -> dict[str, Any]:
    import subprocess
    info = {}
    try:
        cwd = Path.cwd()
        for cmd in [
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            ["git", "rev-parse", "HEAD"],
            ["git", "status", "--porcelain"],
            ["git", "log", "--oneline", "-3"],
            ["git", "remote", "get-url", "origin"],
        ]:
            try:
                result = subprocess.run(cmd, capture_output=True, text=True,
                                        timeout=5, shell=platform.system() == "win32")
                key = cmd[1].replace("-", "_")
                info[key] = result.stdout.strip() if result.returncode == 0 else "N/A"
            except Exception:
                pass
        info["branch"] = info.pop("rev_parse___abbrev_ref_HEAD", "N/A")
        info["head"] = info.pop("rev_parse__HEAD", "N/A")
        info["status"] = info.get("status", "")[:200]
        info["remote"] = info.pop("remote__get_url_origin", None)
    except Exception:
        pass
    return info


def _collect_hooks() -> dict[str, Any]:
    from draguniteus.hook_runner import HookRunner
    try:
        runner = HookRunner()
        hooks_dir = runner.hooks_dir
        hook_files = []
        if hooks_dir.exists():
            hook_files = [str(f.relative_to(hooks_dir)) for f in hooks_dir.rglob("*") if f.is_file()]
        return {
            "hook_files": hook_files,
            "pretooluse_loaded": True,
            "posttooluse_loaded": True,
        }
    except Exception as e:
        return {"error": str(e)}


def _collect_permissions() -> dict[str, Any]:
    from draguniteus.permissions import PermissionStore
    from draguniteus.config import Config
    try:
        store = PermissionStore(Config())
        return {
            "rules_count": len(store.config.permissions) if hasattr(store.config, "permissions") else 0,
            "mode": store.auto_mode,
        }
    except Exception as e:
        return {"error": str(e)}


def _collect_mcp() -> dict[str, Any]:
    from draguniteus.tools.mcp import MCPClient
    try:
        client = MCPClient()
        servers = {}
        for name, conf in client.servers.items():
            running = name in client._processes
            try:
                alive = client.ping(name) if running else False
            except Exception:
                alive = False
            servers[name] = {
                "type": conf.get("type", "stdio"),
                "command": conf.get("command", ""),
                "running": running,
                "responsive": alive,
            }
        return {"servers": servers, "total": len(servers)}
    except Exception as e:
        return {"error": str(e), "servers": {}}


def _collect_skills() -> dict[str, Any]:
    from draguniteus.tools.skills import load_all_skills
    try:
        skills = load_all_skills()
        return {
            "total": len(skills),
            "names": [s.name for s in skills],
        }
    except Exception as e:
        return {"error": str(e)}


def _collect_self() -> dict[str, Any]:
    """Info about the draguniteus installation itself."""
    try:
        src_root = Path(__file__).parent.parent.parent
        install_root = Path(__file__).parent.parent
        return {
            "version": __version__,
            "src_root": str(src_root),
            "install_root": str(install_root),
            "python": sys.version,
            "platform": platform.system(),
            "platform_release": platform.release(),
        }
    except Exception:
        return {}


def _collect_pattern_library() -> dict[str, Any]:
    from draguniteus.memory.pattern_library import PatternLibrary
    try:
        lib = PatternLibrary()
        stats = lib.get_stats()
        return stats
    except Exception as e:
        return {"error": str(e)}


def _collect_archive() -> dict[str, Any]:
    from draguniteus.memory.conversation_archive import ConversationArchive
    try:
        arch = ConversationArchive()
        return {"total_turns": arch.count()}
    except Exception:
        return {}


def redacted(value: str, show_chars: int = 4) -> str:
    if not value:
        return "(not set)"
    if len(value) <= show_chars * 2:
        return "***"
    return value[:show_chars] + "***" + value[-show_chars:]


# ---------------------------------------------------------------------------
# Full environment dump
# ---------------------------------------------------------------------------

def get_full_environment() -> dict[str, Any]:
    """Return the complete environment as a dict. For /inspect --json and web UI."""
    return {
        "self": _collect_self(),
        "config": _collect_config(),
        "env": _collect_env(),
        "session": _collect_session(),
        "tools": _collect_tools(),
        "git": _collect_git(),
        "hooks": _collect_hooks(),
        "permissions": _collect_permissions(),
        "mcp": _collect_mcp(),
        "skills": _collect_skills(),
        "pattern_library": _collect_pattern_library(),
        "archive": _collect_archive(),
    }


# ---------------------------------------------------------------------------
# Human-readable formatter
# ---------------------------------------------------------------------------

def format_environment(env: dict[str, Any], section: str | None = None) -> str:
    """Format the environment dict as human-readable text.

    If section is provided, only show that section.
    Sections: self, config, env, session, tools, git, hooks, permissions, mcp, skills
    """
    if section:
        formatter = _FORMATTERS.get(section, _format_default)
        return formatter(env.get(section, {}))

    lines = ["## Draguniteus Environment\n"]

    for sec, label in [
        ("self", "Self"),
        ("config", "Config"),
        ("env", "Environment"),
        ("git", "Git"),
        ("session", "Session"),
        ("tools", "Tools"),
        ("hooks", "Hooks"),
        ("permissions", "Permissions"),
        ("mcp", "MCP Servers"),
        ("skills", "Skills"),
        ("pattern_library", "Pattern Library"),
        ("archive", "Archive"),
    ]:
        if sec in env and env[sec]:
            lines.append(f"\n### {label}")
            lines.append(_format_section(sec, env[sec]))

    return "\n".join(lines)


def _format_section(name: str, data: Any) -> str:
    formatter = _FORMATTERS.get(name, _format_default)
    return formatter(data)


def _format_self(data: dict) -> str:
    return (f"  Version: {data.get('version', '?')}\n"
            f"  Python: {data.get('python', '?')[:60]}\n"
            f"  Platform: {data.get('platform', '?')} / {data.get('platform_release', '?')}\n"
            f"  Install root: {data.get('install_root', '?')}")


def _format_config(data: dict) -> str:
    lines = []
    for key in ("model", "effort", "max_tokens", "temperature", "thinking", "betas",
                "base_url", "api_key_prefix"):
        val = data.get(key)
        if val is not None:
            lines.append(f"  {key}: {val}")
    lines.append(f"  config_file: {data.get('config_file', '?')}")
    return "\n".join(lines)


def _format_env(data: dict) -> str:
    return "\n".join(f"  {k}: {v}" for k, v in list(data.items())[:15])


def _format_git(data: dict) -> str:
    if not data:
        return "  (not a git repo)"
    lines = []
    for key in ("branch", "head", "status", "remote"):
        val = data.get(key)
        if val:
            lines.append(f"  {key}: {val}")
    return "\n".join(lines)


def _format_session(data: dict) -> str:
    return (f"  sessions available: {data.get('sessions_available', 0)}\n"
            f"  recent: {data.get('recent_session_ids', [])}")


def _format_tools(data: dict) -> str:
    return (f"  total tools: {data.get('total_tools', 0)}\n"
            f"  tools: {', '.join(data.get('tool_names', [])[:20])}...")


def _format_hooks(data: dict) -> str:
    if "error" in data:
        return f"  error: {data['error']}"
    lines = [f"  hook files: {len(data.get('hook_files', []))}"]
    for f in data.get("hook_files", []):
        lines.append(f"    - {f}")
    return "\n".join(lines)


def _format_permissions(data: dict) -> str:
    if "error" in data:
        return f"  error: {data['error']}"
    return (f"  mode: {data.get('mode', '?')}\n"
            f"  rules: {data.get('rules_count', 0)}")


def _format_mcp(data: dict) -> str:
    if "error" in data:
        return f"  error: {data['error']}"
    servers = data.get("servers", {})
    if not servers:
        return "  no MCP servers configured"
    lines = []
    for name, info in servers.items():
        status = "[OK] running" if info.get("running") else "[FAIL] stopped"
        if info.get("responsive"):
            status += " [OK] responsive"
        lines.append(f"  {name}: {status} ({info.get('type', 'stdio')})")
    return "\n".join(lines)


def _format_skills(data: dict) -> str:
    if "error" in data:
        return f"  error: {data['error']}"
    return (f"  total: {data.get('total', 0)}\n"
            f"  {', '.join(data.get('names', []))}")


def _format_pattern_library(data: dict) -> str:
    if "error" in data:
        return f"  error: {data['error']}"
    return (f"  patterns: {data.get('total', 0)}\n"
            f"  languages: {data.get('by_language', {})}")


def _format_archive(data: dict) -> str:
    return f"  archived turns: {data.get('total_turns', 0)}"


def _format_default(data: Any) -> str:
    if isinstance(data, dict):
        return "\n".join(f"  {k}: {v}" for k, v in data.items() if v)
    return f"  {data}"


_FORMATTERS = {
    "self": _format_self,
    "config": _format_config,
    "env": _format_env,
    "git": _format_git,
    "session": _format_session,
    "tools": _format_tools,
    "hooks": _format_hooks,
    "permissions": _format_permissions,
    "mcp": _format_mcp,
    "skills": _format_skills,
    "pattern_library": _format_pattern_library,
    "archive": _format_archive,
}


# ---------------------------------------------------------------------------
# Doctor - self-diagnosis
# ---------------------------------------------------------------------------

def run_doctor() -> dict[str, Any]:
    """Run all self-checks. Returns dict of check -> status."""
    checks: dict[str, Any] = {}

    # 1. API key
    try:
        cfg = Config()
        if cfg.api_key:
            checks["api_key"] = "[OK] configured (prefix: " + cfg.api_key[:8] + "...)"
        else:
            checks["api_key"] = "[FAIL] NOT CONFIGURED - set ANTHROPIC_API_KEY env var or api_key in config"
    except Exception as e:
        checks["api_key"] = f"[FAIL] error: {e}"

    # 2. Config file
    try:
        cfg_file = DEFAULT_CONFIG_DIR / "settings.json"
        if cfg_file.exists():
            checks["config_file"] = f"[OK] found at {cfg_file}"
        else:
            checks["config_file"] = f"[WARN]  not found at {cfg_file}"
    except Exception as e:
        checks["config_file"] = f"[FAIL] error: {e}"

    # 3. Python version
    py_version = sys.version_info
    if py_version >= (3, 10):
        checks["python"] = f"[OK] {sys.version[:50]}"
    else:
        checks["python"] = f"[FAIL] Python {py_version.major}.{py_version.minor} - need 3.10+"

    # 4. Required packages
    for pkg in ("anthropic", "rich", "typer", "questionary", "yaml"):
        try:
            __import__(pkg)
            checks[f"package:{pkg}"] = f"[OK] installed"
        except ImportError:
            checks[f"package:{pkg}"] = f"[FAIL] NOT INSTALLED - run: pip install {pkg}"

    # 5. Tools import
    try:
        from draguniteus.tools import ALL_TOOLS, TOOL_MAP
        checks["tools"] = f"[OK] {len(ALL_TOOLS)} tools loaded"
    except Exception as e:
        checks["tools"] = f"[FAIL] failed: {e}"

    # 6. Skills
    try:
        from draguniteus.tools.skills import load_all_skills
        skills = load_all_skills()
        checks["skills"] = f"[OK] {len(skills)} skills loaded"
    except Exception as e:
        checks["skills"] = f"[FAIL] error: {e}"

    # 7. MCP servers
    try:
        from draguniteus.tools.mcp import MCPClient
        client = MCPClient()
        if client.servers:
            checks["mcp"] = f"[OK] {len(client.servers)} servers configured"
        else:
            checks["mcp"] = "[WARN]  no servers configured"
    except Exception as e:
        checks["mcp"] = f"[FAIL] error: {e}"

    # 8. Git repo
    try:
        import subprocess
        result = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            capture_output=True, text=True, timeout=5,
            shell=platform.system() == "win32"
        )
        if result.returncode == 0:
            checks["git"] = f"[OK] git repo at {result.stdout.strip()}"
        else:
            checks["git"] = "[WARN]  not a git repo"
    except Exception:
        checks["git"] = "[WARN]  git not available"

    # 9. Hooks directory
    try:
        hooks_dir = Path.home() / ".draguniteus" / "hooks"
        if hooks_dir.exists():
            hook_files = list(hooks_dir.rglob("*.json"))
            checks["hooks"] = f"[OK] {len(hook_files)} hook files found"
        else:
            checks["hooks"] = "[WARN]  no hooks directory"
    except Exception as e:
        checks["hooks"] = f"[FAIL] error: {e}"

    # 10. Session directory
    try:
        sessions_dir = Path.home() / ".draguniteus" / "sessions"
        if sessions_dir.exists():
            sessions = list(sessions_dir.glob("*.jsonl"))
            checks["sessions"] = f"[OK] {len(sessions)} sessions found"
        else:
            checks["sessions"] = "[WARN]  no sessions directory"
    except Exception as e:
        checks["sessions"] = f"[FAIL] error: {e}"

    # Summary
    passed = sum(1 for v in checks.values() if str(v).startswith("[OK]"))
    failed = sum(1 for v in checks.values() if str(v).startswith("[FAIL]"))
    warned = sum(1 for v in checks.values() if str(v).startswith("[WARN]"))
    checks["_summary"] = f"{passed} passed, {failed} failed, {warned} warnings"

    return checks


def format_doctor(checks: dict[str, Any]) -> str:
    """Format doctor output as readable text."""
    lines = ["## Draguniteus Doctor - Self-Diagnosis\n"]
    for key, val in checks.items():
        if key.startswith("_"):
            continue
        lines.append(f"  {val}")
    lines.append(f"\n{checks.get('_summary', '')}")
    return "\n".join(lines)