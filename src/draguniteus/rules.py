"""Rules system: path-scoped rules loaded from .draguniteus/rules/*.md."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pathspec
import yaml

# Patterns that indicate instruction injection attempts
_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+all\s+previous\s+instructions", re.IGNORECASE),
    re.compile(r"disregard\s+all\s+prior\s+rules", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+a\s+different\s+ai", re.IGNORECASE),
    re.compile(r"pretend\s+you\s+are\s+.*?instead", re.IGNORECASE),
    re.compile(r"override\s+your\s+(system\s+)?instructions", re.IGNORECASE),
    re.compile(r"discard\s+your\s+(system\s+)?prompt", re.IGNORECASE),
    re.compile(r"forget\s+everything\s+above", re.IGNORECASE),
    re.compile(r"new\s+system\s+prompt", re.IGNORECASE),
]

# Control characters that could cause terminal injection
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _sanitize_content(content: str) -> str:
    """Sanitize rule content to prevent injection and control-char attacks.

    Removes instruction-override patterns and terminal control characters.
    """
    for pattern in _INJECTION_PATTERNS:
        content = pattern.sub("[FILTERED]", content)
    content = _CONTROL_CHARS.sub("", content)
    return content


class Rule:
    """A single rule loaded from a .md file with frontmatter."""

    def __init__(
        self,
        name: str,
        content: str,
        paths: list[str],
        description: str | None = None,
    ):
        self.name = name
        self.content = content
        self.paths = paths  # Glob patterns
        self.description = description


class RulesManager:
    """Manages path-scoped rules loaded from .draguniteus/rules/ directory."""

    def __init__(self, project_dir: Path | None = None):
        self.project_dir = project_dir or Path.cwd()
        self.rules_dir = self.project_dir / ".draguniteus" / "rules"
        self._rules: list[Rule] = []
        self._pathspecs: dict[str, pathspec.PathSpec] = {}
        self._load()

    def _load(self) -> None:
        """Load all .md rule files from the rules directory."""
        if not self.rules_dir.exists():
            return

        for md_file in self.rules_dir.glob("*.md"):
            try:
                rule = self._load_rule_file(md_file)
                if rule:
                    self._rules.append(rule)
                    # Build pathspec for this rule's paths
                    if rule.paths:
                        self._pathspecs[rule.name] = pathspec.PathSpec.from_paths(
                            rule.paths
                        )
            except Exception:
                continue

    def _load_rule_file(self, path: Path) -> Rule | None:
        """Load a single rule file with YAML frontmatter."""
        try:
            content = path.read_text(encoding="utf-8")
        except Exception:
            return None

        # Parse frontmatter
        frontmatter_match = re.match(r"^---\n(.*?)\n---\n(.*)", content, re.DOTALL)
        if not frontmatter_match:
            return None

        try:
            frontmatter = yaml.safe_load(frontmatter_match.group(1))
            body = frontmatter_match.group(2).strip()
        except Exception:
            return None

        name = frontmatter.get("name", path.stem)
        description = frontmatter.get("description")
        paths = frontmatter.get("paths", [])

        # paths can be a string or list
        if isinstance(paths, str):
            paths = [paths]

        return Rule(
            name=name,
            content=body,
            paths=paths,
            description=description,
        )

    def get_applicable_rules(self, file_path: str | Path) -> list[Rule]:
        """Get rules that apply to the given file path."""
        applicable = []
        for rule in self._rules:
            if not rule.paths:
                # Rule with no paths applies everywhere
                applicable.append(rule)
                continue

            # Check if file matches any of the rule's paths
            for pattern in rule.paths:
                # Use fnmatch-style glob matching
                if self._matches_glob(pattern, str(file_path)):
                    applicable.append(rule)
                    break

        return applicable

    def _matches_glob(self, pattern: str, file_path: str) -> bool:
        """Check if file_path matches the glob pattern."""
        import fnmatch
        return fnmatch.fnmatch(file_path, pattern) or fnmatch.fnmatch(
            file_path, f"**/{pattern}"
        ) or fnmatch.fnmatch(file_path, f"**/{pattern}/**")

    def inject_for_paths(self, file_paths: list[str | Path]) -> str:
        """Build a rules injection string for the given file paths.

        Sanitizes all rule content before injection to prevent instruction Override.
        """
        injected = []
        for fp in file_paths:
            rules = self.get_applicable_rules(fp)
            for rule in rules:
                if rule not in injected:
                    injected.append(rule)

        if not injected:
            return ""

        parts = ["\n\n## Applicable Rules\n"]
        for rule in injected:
            # Sanitize content to prevent injection attacks
            safe_content = _sanitize_content(rule.content)
            parts.append(f"\n### {rule.name}\n{safe_content}")

        return "\n".join(parts)

    def list_rules(self) -> list[dict[str, Any]]:
        """List all loaded rules with their metadata."""
        return [
            {
                "name": r.name,
                "description": r.description or "",
                "paths": r.paths,
            }
            for r in self._rules
        ]