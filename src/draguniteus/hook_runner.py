"""Hook runner: executes all hook events via the hookify rule engine."""
from __future__ import annotations

import fnmatch
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

# Try to import from installed hooks package, fall back to project .draguniteus/hooks/core
try:
    from draguniteus.hooks.core.config_loader import load_rules
    from draguniteus.hooks.core.rule_engine import RuleEngine
except ImportError:
    # Fallback: add project .draguniteus/hooks to path
    _project_hooks = Path(__file__).parent.parent / ".draguniteus" / "hooks"
    if (_project_hooks / "core").exists():
        sys.path.insert(0, str(_project_hooks))
        try:
            from core.config_loader import load_rules
            from core.rule_engine import RuleEngine
        except ImportError:
            load_rules = None
            RuleEngine = None
    else:
        load_rules = None
        RuleEngine = None

_HOOK_SCRIPT_DIR = Path(__file__).parent.parent.parent / ".draguniteus" / "hooks"
_HOOK_JSON = _HOOK_SCRIPT_DIR / "hooks.json"


# Supported hook events
HOOK_EVENTS = [
    "PreToolUse", "PostToolUse", "Stop", "SubagentStop",
    "SessionStart", "SessionEnd", "UserPromptSubmit", "PreCompact", "Notification"
]


def _load_hook_config() -> dict[str, Any]:
    """Load hooks.json configuration."""
    if not _HOOK_JSON.exists():
        return {}
    try:
        return json.loads(_HOOK_JSON.read_text())
    except Exception as e:
        import logging
        logging.getLogger("draguniteus.hooks").warning(f"Failed to load hooks config: {e}")
        return {}


def _matcher_matches(matcher: str, value: str) -> bool:
    """Check if a matcher pattern matches a value.

    Supports:
    - Exact: "Write"
    - Multiple: "Write|Edit|Glob"
    - Wildcard: "*"
    - Regex: "mcp__.*__delete.*" (detected by regex special chars)
    """
    if not matcher or matcher == "*":
        return True

    # Pipe-separated multiple
    if "|" in matcher:
        return any(_matcher_matches(m.strip(), value) for m in matcher.split("|"))

    # Check if it's a regex pattern (contains regex-specific chars)
    regex_chars = {"(", ")", "[", "]", "{", "}", "^", "$", "+", ".", "?"}
    if any(c in matcher for c in regex_chars) and not fnmatch.fnmatch(matcher, matcher):
        # Looks like regex, not glob
        try:
            return bool(re.search(matcher, value))
        except re.error:
            pass

    # Simple string or glob match
    return fnmatch.fnmatch(value, matcher) or value == matcher


def _run_hook_script(script_path: Path, input_data: dict[str, Any]) -> dict[str, Any]:
    """Run a hook script with JSON input, return JSON output."""
    import logging
    logger = logging.getLogger("draguniteus.hooks")
    try:
        env = os.environ.copy()
        env["DRAGUNITEUS_PLUGIN_ROOT"] = str(_HOOK_SCRIPT_DIR.parent)

        # Use sys.executable for cross-platform compatibility
        python_exec = sys.executable
        result = subprocess.run(
            [python_exec, str(script_path)],
            input=json.dumps(input_data),
            capture_output=True,
            text=True,
            timeout=15,
            env=env,
        )
        if result.returncode == 0 and result.stdout.strip():
            return json.loads(result.stdout)
        elif result.returncode != 0:
            logger.warning(f"Hook script {script_path.name} exited with code {result.returncode}: {result.stderr[:200]}")
    except Exception as e:
        logger.warning(f"Hook script {script_path.name} failed: {e}")
    return {}


def _get_hook_event(tool_name: str) -> str:
    """Map tool name to hook event type for inline rule engine."""
    if tool_name == "Bash":
        return "bash"
    elif tool_name in ("Edit", "Write", "MultiEdit"):
        return "file"
    return "all"


def _resolve_script_path(hook_command: str, hooks_dir: Path) -> Path | None:
    """Resolve a hook command string to an actual script path."""
    # Handle "python3 script.py" or "bash script.sh" patterns
    parts = hook_command.split()
    if not parts:
        return None
    # Get the script path (last part or after the interpreter)
    script_name = parts[-1].strip('"').strip("'")
    script_path = hooks_dir / script_name
    if script_path.exists():
        return script_path
    # Try as absolute path
    abs_path = Path(script_name)
    if abs_path.exists():
        return abs_path
    return None


class HookRunner:
    """Manages hook execution for all hook events."""

    def __init__(self, hooks_dir: Path | None = None):
        self.hooks_dir = hooks_dir or _HOOK_SCRIPT_DIR
        self._config = _load_hook_config()
        self._plugin_hooks: dict[str, list[dict]] = {}

    def register_plugin_hooks(self, event_name: str, hooks: list[dict]) -> None:
        """Register hooks from a plugin."""
        if event_name not in self._plugin_hooks:
            self._plugin_hooks[event_name] = []
        self._plugin_hooks[event_name].extend(hooks)

    def _run_hooks_for_event(
        self,
        event_name: str,
        input_data: dict[str, Any],
        matcher_key: str | None = None,
        matcher_value: str = "*",
    ) -> dict[str, Any]:
        """Run hooks for a specific event, returning first non-empty result."""
        # Check config hooks first
        hook_configs = []

        # User-level hooks from config
        event_hooks = self._config.get("hooks", {}).get(event_name, [])
        hook_configs.extend(event_hooks)

        # Plugin hooks
        if event_name in self._plugin_hooks:
            hook_configs.extend(self._plugin_hooks[event_name])

        for hook_entry in hook_configs:
            # Check matcher
            if matcher_key and hook_entry.get("matcher"):
                if not _matcher_matches(hook_entry["matcher"], matcher_value):
                    continue

            for hook in hook_entry.get("hooks", []):
                hook_type = hook.get("type", "")

                if hook_type == "command":
                    script_path = _resolve_script_path(hook.get("command", ""), self.hooks_dir)
                    if script_path and script_path.exists():
                        result = _run_hook_script(script_path, input_data)
                        if result:
                            return result

                elif hook_type == "prompt":
                    # Inline prompt-based hook — these are user-confirmation hooks
                    # that would require interactive REPL access to execute properly.
                    # Log the intent but don't block (return empty to continue).
                    prompt_msg = hook.get("message", "")
                    if prompt_msg:
                        import logging
                        logging.getLogger("draguniteus.hooks").debug(
                            f"Prompt hook triggered: {prompt_msg[:100]}"
                        )

        return {}

    def run_pretooluse(self, tool_name: str, tool_input: dict[str, Any], tool_input_json: str = "") -> dict[str, Any]:
        """Run PreToolUse hooks. Returns dict with keys:
        - block: bool — whether to block the tool
        - systemMessage: str — message to display
        - hookSpecificOutput: dict — hook-specific response
        """
        input_data = {
            "tool_name": tool_name,
            "tool_input": tool_input,
            "tool_input_json": tool_input_json,
            "hook_event_name": "PreToolUse",
        }

        result = self._run_hooks_for_event("PreToolUse", input_data, "matcher", tool_name)
        if result:
            return result

        # Fall back to inline rule engine
        return self._run_inline_pretooluse(tool_name, tool_input)

    # Alias for compatibility
    run_prettooluse = run_pretooluse

    def _run_inline_pretooluse(self, tool_name: str, tool_input: dict[str, Any]) -> dict[str, Any]:
        """Run PreToolUse hooks inline using rule engine."""
        if RuleEngine is None or load_rules is None:
            return {}

        try:
            # Determine event type from tool name
            event = _get_hook_event(tool_name)
            rules = load_rules(event=event)
            if not rules:
                return {}

            engine = RuleEngine()
            input_data = {
                "tool_name": tool_name,
                "tool_input": tool_input,
                "hook_event_name": "PreToolUse",
            }
            return engine.evaluate_rules(rules, input_data)
        except Exception:
            return {}

    def run_posttooluse(self, tool_name: str, tool_input: dict[str, Any], result: str) -> dict[str, Any]:
        """Run PostToolUse hooks."""
        input_data = {
            "tool_name": tool_name,
            "tool_input": tool_input,
            "tool_result": result,
            "hook_event_name": "PostToolUse",
        }
        return self._run_hooks_for_event("PostToolUse", input_data, "matcher", tool_name)

    def run_stop(self, messages: list[dict], reason: str) -> dict[str, Any]:
        """Run Stop hooks when agent is about to stop."""
        input_data = {
            "messages": messages[-10:],
            "reason": reason,
            "hook_event_name": "Stop",
        }
        return self._run_hooks_for_event("Stop", input_data)

    def run_subagentstop(self, agent_name: str, result: str) -> dict[str, Any]:
        """Run SubagentStop hooks when a subagent completes."""
        input_data = {
            "agent_name": agent_name,
            "result": result,
            "hook_event_name": "SubagentStop",
        }
        return self._run_hooks_for_event("SubagentStop", input_data)

    def run_session_start(self, session_id: str, cwd: str) -> dict[str, Any]:
        """Run SessionStart hooks when REPL session begins."""
        input_data = {
            "session_id": session_id,
            "cwd": cwd,
            "hook_event_name": "SessionStart",
        }
        return self._run_hooks_for_event("SessionStart", input_data)

    def run_session_end(self, session_id: str, cwd: str) -> dict[str, Any]:
        """Run SessionEnd hooks when REPL session ends."""
        input_data = {
            "session_id": session_id,
            "cwd": cwd,
            "hook_event_name": "SessionEnd",
        }
        return self._run_hooks_for_event("SessionEnd", input_data)

    # Aliases for snake_case compatibility
    run_sessionstart = run_session_start
    run_sessionend = run_session_end

    def run_userpromptsubmit(self, prompt: str) -> dict[str, Any]:
        """Run UserPromptSubmit hooks when user submits a prompt."""
        input_data = {
            "prompt": prompt,
            "hook_event_name": "UserPromptSubmit",
        }
        return self._run_hooks_for_event("UserPromptSubmit", input_data)

    def run_precompact(self, messages: list[dict]) -> dict[str, Any]:
        """Run PreCompact hooks before message history compaction."""
        input_data = {
            "messages": messages,
            "hook_event_name": "PreCompact",
        }
        return self._run_hooks_for_event("PreCompact", input_data)

    def run_notification(self, notification: str) -> dict[str, Any]:
        """Run Notification hooks when a notification is sent."""
        input_data = {
            "notification": notification,
            "hook_event_name": "Notification",
        }
        return self._run_hooks_for_event("Notification", input_data)


# Global hook runner instance
_hook_runner: HookRunner | None = None


def get_hook_runner() -> HookRunner:
    global _hook_runner
    if _hook_runner is None:
        _hook_runner = HookRunner()
    return _hook_runner