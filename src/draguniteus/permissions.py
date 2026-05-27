"""Permission system: ask / auto-approve / deny rules, auto mode classifier, sandboxing."""
from __future__ import annotations

import fnmatch
import json
import os
import platform
import re
import subprocess
from pathlib import Path
from typing import Any

from draguniteus.config import Config, DEFAULT_CONFIG_DIR


class Permission:
    def __init__(self, tool: str, pattern: str, action: str, detail_pattern: str | None = None):
        self.tool = tool
        self.pattern = pattern  # The tool pattern (e.g., "Bash", "Bash(git *)")
        self.action = action  # "ask" | "auto_approve" | "deny"
        self.detail_pattern = detail_pattern  # Optional detail regex pattern

    def matches_tool(self, tool: str) -> bool:
        """Check if this permission matches the given tool name."""
        if self.tool == "*":
            return True
        # Handle syntax like "Bash(git *)", "Edit(**/*.ts)", "Write(*)"
        if '(' in self.tool:
            tool_name = self.tool.split('(')[0]
            return tool_name == tool
        return self.tool == tool


class PermissionClassifier:
    """Background classifier for Auto Mode — classifies commands as safe/risky."""

    DEFAULT_RULES = [
        {"pattern": r"rm\s+-rf\s+/(?!proc|sys)", "action": "block", "reason": "recursive root delete"},
        {"pattern": r"rm\s+-rf\s+/\*", "action": "block", "reason": "recursive root delete"},
        {"pattern": r"mkfs", "action": "block", "reason": "filesystem creation"},
        {"pattern": r"dd\s+if=.*of=/dev/", "action": "block", "reason": "raw device write"},
        {"pattern": r"curl.*\|(sh|bash)", "action": "block", "reason": "pipe to shell"},
        {"pattern": r"wget.*\|(sh|bash)", "action": "block", "reason": "pipe to shell"},
        {"pattern": r":\(\)\{.*\}\s*;.*#", "action": "block", "reason": "bash fork bomb"},
        {"pattern": r"git\s+push\s+--force", "action": "warn", "reason": "force push"},
        {"pattern": r"npm\s+i\s+-g", "action": "warn", "reason": "global npm install"},
        {"pattern": r"pip\s+install\s+--user", "action": "warn", "reason": "user pip install"},
        {"pattern": r"sudo\s+", "action": "warn", "reason": "sudo command"},
        {"pattern": r"chmod\s+777", "action": "warn", "reason": "world-writable permissions"},
    ]

    def __init__(self, rules_file: Path | None = None):
        self.rules: list[dict[str, Any]] = []
        self.rules_file = rules_file or (DEFAULT_CONFIG_DIR / "auto_mode_rules.json")
        self._load()

    def _load(self) -> None:
        if self.rules_file.exists():
            try:
                with open(self.rules_file, "r", encoding="utf-8") as f:
                    self.rules = json.load(f)
            except (json.JSONDecodeError, ValueError):
                self.rules = list(self.DEFAULT_RULES)
        else:
            self.rules = list(self.DEFAULT_RULES)

    def classify(self, tool: str, detail: str) -> tuple[str, str | None]:
        """Classify a command. Returns (action, reason)."""
        for rule in self.rules:
            try:
                if re.search(rule["pattern"], detail):
                    return rule.get("action", "ask"), rule.get("reason")
            except re.error:
                continue
        return "ask", None

    def auto_approve(self, tool: str, detail: str) -> bool:
        """Returns True if command should be auto-approved in auto mode."""
        action, _ = self.classify(tool, detail)
        return action == "allow"

    def block(self, tool: str, detail: str) -> bool:
        """Returns True if command should be blocked in auto mode."""
        action, _ = self.classify(tool, detail)
        return action == "block"

    def warn(self, tool: str, detail: str) -> bool:
        """Returns True if command should warn in auto mode."""
        action, _ = self.classify(tool, detail)
        return action == "warn"

    @staticmethod
    def default_rules_json() -> str:
        """Return default rules as formatted JSON."""
        return json.dumps(PermissionClassifier.DEFAULT_RULES, indent=2)


class SandboxConfig:
    """Sandbox configuration for Bash tool."""

    def __init__(self, config: Config | None = None):
        self.filesystem_enabled = False
        self.network_enabled = True
        self.allowed_paths: list[str] = ["."]
        self.max_output_size = 1024 * 1024  # 1MB
        self.max_runtime = 300  # 5 minutes
        if config:
            sandbox = config._raw.get("sandbox", {})
            self.filesystem_enabled = sandbox.get("filesystem", False)
            self.network_enabled = sandbox.get("network", True)
            self.allowed_paths = sandbox.get("allowed_paths", ["."])

    def is_network_blocked(self, command: str) -> bool:
        """Check if command initiates network connection."""
        if not self.network_enabled:
            return True
        blocked_patterns = [
            r"\bcurl\b", r"\bwget\b", r"\bnc\b", r"\bnetcat\b",
            r"\bssh\b", r"\bscp\b", r"\brsync\b", r"\btelnet\b",
            r"\bftp\b", r"\bwget\b", r"\bcurl\b",
        ]
        for pattern in blocked_patterns:
            if re.search(pattern, command):
                return True
        return False

    def is_path_safe(self, command: str, cwd: Path) -> bool:
        """Check if command only accesses allowed paths."""
        if not self.filesystem_enabled:
            return True
        # Extract paths from command
        path_pattern = re.compile(r"['\"]?([/\w][^\s'\";]*)['\"]?")
        for match in path_pattern.finditer(command):
            path = Path(match.group(1)).expanduser()
            if path.is_absolute():
                # Check if path is in allowed_paths
                allowed = False
                for ap in self.allowed_paths:
                    allowed_root = Path(ap).expanduser().resolve()
                    try:
                        path.resolve().relative_to(allowed_root.resolve())
                        allowed = True
                        break
                    except ValueError:
                        continue
                if not allowed and not path.name.startswith('.'):
                    return False
        return True


class PermissionStore:
    """Layered permission rules: global → project → session."""

    def __init__(self, config: Config, auto_mode: bool = False):
        self.config = config
        self.auto_mode = auto_mode
        self._rules: list[Permission] = []
        self._session_approved: dict[str, bool] = {}  # tool+pattern → approved
        self._classifier = PermissionClassifier()
        self._sandbox = SandboxConfig(config)
        self._load()

    def _load(self) -> None:
        """Load rules from global + project permissions files."""
        raw_list = self.config.load_permissions()
        for item in raw_list:
            p = Permission(
                tool=item.get("tool", ""),
                pattern=item.get("pattern", "*"),
                action=item.get("action", "ask"),
            )
            self._rules.append(p)

        # Also load project-level if present
        project_pf = Config.project_dir() / "permissions.json"
        if project_pf.exists():
            with open(project_pf, "r", encoding="utf-8") as f:
                project_rules = json.load(f)
            for item in project_rules:
                self._rules.append(Permission(
                    tool=item.get("tool", ""),
                    pattern=item.get("pattern", "*"),
                    action=item.get("action", "ask"),
                ))

    def check(self, tool: str, detail: str) -> str:
        """Return 'allow', 'block', or 'ask'."""
        # Check session cache first
        cache_key = f"{tool}:{detail[:80]}"
        if cache_key in self._session_approved:
            return "allow"

        # In auto mode, use classifier first
        if self.auto_mode:
            classifier_action, reason = self._classifier.classify(tool, detail)
            if classifier_action == "block":
                return "deny"
            elif classifier_action == "allow":
                return "allow"
            # classifier_action == "warn" falls through to normal rules
            # classifier_action == "ask" falls through to normal rules

        # Check sandbox restrictions
        if tool == "Bash":
            if not self._sandbox.network_enabled and self._sandbox.is_network_blocked(detail):
                return "deny"
            if self._sandbox.filesystem_enabled and not self._sandbox.is_path_safe(detail, Path.cwd()):
                return "deny"

        # Check deny rules first (deny takes precedence over allow)
        for rule in self._rules:
            if not rule.matches_tool(tool):
                continue
            if rule.action == "deny" and self._matches_rule_pattern(rule, detail):
                return "deny"

        # Then check allow/auto_approve rules (first matching wins)
        for rule in self._rules:
            if not rule.matches_tool(tool):
                continue
            if rule.action in ("auto_approve", "allow") and self._matches_rule_pattern(rule, detail):
                return "allow"

        return "ask"

    def _matches_rule_pattern(self, rule: Permission, detail: str) -> bool:
        """Check if rule's pattern matches the detail."""
        # Extract detail suffix from tool name (e.g. "Write(*.md)" -> "*.md")
        tool_pattern = rule.tool
        detail_suffix = None
        if '(' in tool_pattern:
            inner = tool_pattern.split('(', 1)[1].rstrip(')')
            if inner != '*':
                detail_suffix = inner

        # Also check pattern field for backward compat
        pattern = rule.pattern
        if '(' in pattern:
            inner = pattern.split('(', 1)[1].rstrip(')')
            if inner != '*':
                detail_suffix = inner

        # If we have a detail suffix from either source, use it
        if detail_suffix:
            try:
                return bool(re.search(detail_suffix, detail))
            except re.error:
                return fnmatch.fnmatch(detail, detail_suffix)
        # Simple pattern match
        return self._matches(pattern, detail)

    def _matches(self, pattern: str, text: str) -> bool:
        """Regex-based matching for flexible patterns."""
        try:
            return bool(re.search(pattern, text))
        except re.error:
            # Fall back to fnmatch if pattern is not a valid regex
            return fnmatch.fnmatch(text, pattern)

    def remember_approval(self, tool: str, detail: str) -> None:
        """Cache an approval for this session."""
        key = f"{tool}:{detail[:80]}"
        self._session_approved[key] = True

    def remember_deny(self, tool: str, detail: str) -> None:
        """Cache a denial for this session."""
        key = f"{tool}:{detail[:80]}"
        self._session_approved[key] = False

    def add_rule(self, tool: str, pattern: str, action: str) -> None:
        """Add a permanent rule (saved to permissions.json)."""
        self._rules.append(Permission(tool, pattern, action))

    def save(self) -> None:
        """Persist current rules to permissions.json."""
        from draguniteus.config import DEFAULT_CONFIG_DIR
        DEFAULT_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        pf = self.default_permissions_file()
        rules_data = [
            {"tool": r.tool, "pattern": r.pattern, "action": r.action}
            for r in self._rules
            if r.tool != "*"  # Don't persist wildcard catch-all rules
        ]
        try:
            with open(pf, "w", encoding="utf-8") as f:
                json.dump(rules_data, f, indent=2)
        except Exception:
            pass

    @staticmethod
    def default_permissions_file() -> Path:
        """Return path to default permissions file."""
        from draguniteus.config import DEFAULT_CONFIG_DIR
        return DEFAULT_CONFIG_DIR / "permissions.json"

    @staticmethod
    def create_defaults() -> None:
        """Create a default permissions.json with safe defaults."""
        defaults = [
            {"tool": "Bash", "pattern": "rm -rf /*", "action": "deny"},
            {"tool": "Bash", "pattern": "rm -rf /", "action": "deny"},
            {"tool": "Bash", "pattern": "format.*:", "action": "deny"},
            {"tool": "Bash", "pattern": "mkfs", "action": "deny"},
            {"tool": "Bash", "pattern": "dd if=.*of=/dev/", "action": "deny"},
            {"tool": "Bash", "pattern": "curl.*|sh", "action": "deny"},
            {"tool": "Bash", "pattern": "wget.*|sh", "action": "deny"},
            {"tool": "Bash", "pattern": "curl.*bash", "action": "deny"},
            {"tool": "Bash", "pattern": "pip install .*", "action": "auto_approve"},
            {"tool": "Bash", "pattern": "git add .", "action": "auto_approve"},
            {"tool": "Bash", "pattern": "git commit .*", "action": "auto_approve"},
            {"tool": "Bash", "pattern": "npm install.*", "action": "auto_approve"},
            {"tool": "Bash", "pattern": "npm run.*", "action": "auto_approve"},
            {"tool": "Bash", "pattern": "python.*", "action": "auto_approve"},
            {"tool": "Bash", "pattern": "pytest.*", "action": "auto_approve"},
            {"tool": "Bash", "pattern": "ls.*", "action": "auto_approve"},
            {"tool": "Bash", "pattern": "cat.*", "action": "auto_approve"},
            {"tool": "Bash", "pattern": "find.*", "action": "auto_approve"},
            {"tool": "Bash", "pattern": "git status.*", "action": "auto_approve"},
            {"tool": "Bash", "pattern": "git diff.*", "action": "auto_approve"},
            {"tool": "Read", "pattern": "*", "action": "auto_approve"},
            {"tool": "Write", "pattern": "*", "action": "ask"},
            {"tool": "Edit", "pattern": "*", "action": "ask"},
            # Granular rules examples
            {"tool": "Bash(git *)", "pattern": "*", "action": "auto_approve"},
            {"tool": "Bash(npm *)", "pattern": "*", "action": "auto_approve"},
        ]

        pf = PermissionStore.default_permissions_file()
        pf.parent.mkdir(parents=True, exist_ok=True)
        with open(pf, "w", encoding="utf-8") as f:
            json.dump(defaults, f, indent=2)