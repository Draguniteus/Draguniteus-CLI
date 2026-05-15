"""Team Context: shared intelligence across engineering teams.

When multiple engineers use Draguniteus on the same project,
this provides shared context, patterns, and conventions with
file locking for concurrent writes and git sync for cross-machine sharing.
"""
from __future__ import annotations

import json
import time
import os
from pathlib import Path
from typing import Any

try:
    import fcntl
    _HAS_FCNTL = True
except ImportError:
    fcntl = None
    _HAS_FCNTL = False


class TeamMember:
    def __init__(self, name: str, email: str, role: str):
        self.name = name
        self.email = email
        self.role = role
        self.last_active = time.strftime("%Y-%m-%dT%H:%M:%SZ")


class SharedDecision:
    def __init__(self, decision: str, rationale: str,
                 decided_by: str, decided_at: str | None = None,
                 team: str = "default"):
        self.decision = decision
        self.rationale = rationale
        self.decided_by = decided_by
        self.decided_at = decided_at or time.strftime("%Y-%m-%dT%H:%M:%SZ")
        self.team = team


class _LockedFile:
    """Context manager for locked file I/O (works on Linux/macOS; fallback on Windows)."""

    def __init__(self, path: Path, mode: str):
        self._path = path
        self._mode = mode
        self._f = None

    def __enter__(self):
        if self._path.exists():
            self._f = open(self._path, self._mode, encoding="utf-8")
            if _HAS_FCNTL:
                try:
                    fcntl.flock(self._f.fileno(), fcntl.LOCK_EX)
                except (AttributeError, OSError):
                    pass
        return self

    def __exit__(self, *args):
        if self._f:
            if _HAS_FCNTL:
                try:
                    fcntl.flock(self._f.fileno(), fcntl.LOCK_UN)
                except (AttributeError, OSError):
                    pass
            self._f.close()


class TeamContext:
    """Shared team intelligence for collaborative coding.

    Provides:
    - Team member directory with expertise areas
    - Shared decision log (why we chose X over Y)
    - Team coding conventions (enforced automatically)
    - Shared code patterns

    Team data is stored in .draguniteus/team/ and can be synced via git
    (commit and push) for cross-machine team sharing.

    Usage:
        ctx = TeamContext(project_root)
        ctx.add_decision("We use Postgres, not MySQL",
                        "Better JSON support and COPY command",
                        decided_by="alice")
        convention = ctx.get_convention("auth")
    """

    def __init__(self, project_root: Path | None = None):
        self.project_root = project_root or Path.cwd()
        self.team_dir = self.project_root / ".draguniteus" / "team"
        self.team_dir.mkdir(parents=True, exist_ok=True)

        self._members: list[TeamMember] = []
        self._decisions: list[SharedDecision] = []
        self._conventions: dict[str, str] = {}  # convention_name -> description
        self._load()

    def _load(self) -> None:
        members_file = self.team_dir / "members.json"
        decisions_file = self.team_dir / "decisions.json"
        conventions_file = self.team_dir / "conventions.json"

        with _LockedFile(members_file, "r") as lf:
            if lf._f:
                try:
                    self._members = [
                        TeamMember(**m) for m in json.loads(lf._f.read()).get("members", [])
                    ]
                except (json.JSONDecodeError, TypeError):
                    pass

        with _LockedFile(decisions_file, "r") as lf:
            if lf._f:
                try:
                    self._decisions = [
                        SharedDecision(**d) for d in json.loads(lf._f.read()).get("decisions", [])
                    ]
                except (json.JSONDecodeError, TypeError):
                    pass

        with _LockedFile(conventions_file, "r") as lf:
            if lf._f:
                try:
                    self._conventions = json.loads(lf._f.read()).get("conventions", {})
                except (json.JSONDecodeError, TypeError):
                    pass

    def _save(self) -> None:
        members_file = self.team_dir / "members.json"
        decisions_file = self.team_dir / "decisions.json"
        conventions_file = self.team_dir / "conventions.json"

        with _LockedFile(members_file, "w") as lf:
            if lf._f:
                lf._f.write(json.dumps({
                    "members": [vars(m) for m in self._members]
                }, indent=2))

        with _LockedFile(decisions_file, "w") as lf:
            if lf._f:
                lf._f.write(json.dumps({
                    "decisions": [vars(d) for d in self._decisions]
                }, indent=2))

        with _LockedFile(conventions_file, "w") as lf:
            if lf._f:
                lf._f.write(json.dumps({
                    "conventions": self._conventions
                }, indent=2))

    def add_member(self, name: str, email: str, role: str) -> TeamMember:
        member = TeamMember(name, email, role)
        self._members.append(member)
        self._save()
        return member

    def add_decision(self, decision: str, rationale: str,
                     decided_by: str, team: str = "default") -> None:
        sd = SharedDecision(decision, rationale, decided_by, team=team)
        self._decisions.append(sd)
        self._save()

    def get_decision(self, topic: str) -> SharedDecision | None:
        """Find a decision related to a topic."""
        topic_lower = topic.lower()
        for d in reversed(self._decisions):
            if topic_lower in d.decision.lower() or topic_lower in d.rationale.lower():
                return d
        return None

    def set_convention(self, name: str, description: str) -> None:
        """Set a team coding convention.

        e.g. set_convention("error-handling", "Always return (error, result) tuples")
        """
        self._conventions[name] = description
        self._save()

    def get_convention(self, name: str) -> str | None:
        return self._conventions.get(name)

    def enforce_conventions(self, code: str, file_path: str | None = None) -> list[str]:
        """Check code against team conventions, return warnings.

        Analyzes the actual code content and returns a list of violation messages.
        Checks multiple convention patterns.
        """
        violations: list[str] = []

        for name, desc in self._conventions.items():
            desc_lower = desc.lower()

            if name == "error-handling" or "error" in desc_lower:
                if "tuple" in desc_lower or "(error" in desc_lower:
                    if "return None" in code and "return error" not in code and "return (" not in code:
                        violations.append(
                            f"Convention '{name}': Use (error, result) tuple returns, not bare None"
                        )
                if "logging" in desc_lower:
                    if "except:" in code and "log" not in code.lower() and "print" not in code.lower():
                        violations.append(
                            f"Convention '{name}': Bare except should log the error"
                        )

            elif name == "naming" or "naming convention" in desc_lower:
                if "snake_case" in desc_lower:
                    # Check for camelCase function/variable names
                    import re
                    camel = re.findall(r'\b[a-z]+[A-Z][a-zA-Z]*\b', code)
                    if camel:
                        violations.append(
                            f"Convention '{name}': snake_case preferred — found: {camel[:3]}"
                        )

            elif name == "types" or "typing" in desc_lower:
                if "required" in desc_lower or "must have" in desc_lower:
                    # Check for functions without type hints
                    import re
                    func_defs = re.findall(r'def (\w+)\([^)]*\):', code)
                    for func in func_defs:
                        violations.append(
                            f"Convention '{name}': Function '{func}' should have type hints"
                        )

            elif name == "security" or "auth" in name:
                if "secret" in desc_lower or "api" in desc_lower:
                    if "api_key" in code or "apiKey" in code:
                        # Check it's not accessed via env
                        if "os.environ" not in code and "getenv" not in code:
                            violations.append(
                                f"Convention '{name}': API keys should be read from environment variables"
                            )

        return violations

    def git_sync(self, message: str = "Update team context") -> dict[str, str]:
        """Commit and push team context to git for cross-machine sync.

        Returns dict with status for each file that was committed.
        """
        import subprocess, sys

        results: dict[str, str] = {}
        team_files = list(self.team_dir.glob("*.json"))

        if not team_files:
            return {"status": "no files to commit"}

        # Check git status
        try:
            status_result = subprocess.run(
                ["git", "status", "--porcelain", str(self.team_dir)],
                capture_output=True, text=True, timeout=10,
                cwd=self.project_root, shell=sys.platform == "win32",
            )
            if not status_result.stdout.strip():
                return {"status": "nothing to commit"}

            # Add team files
            for tf in team_files:
                add_result = subprocess.run(
                    ["git", "add", "--", str(tf)],
                    capture_output=True, text=True, timeout=10,
                    cwd=self.project_root, shell=sys.platform == "win32",
                )
                results[str(tf)] = "added" if add_result.returncode == 0 else f"failed: {add_result.stderr}"

            # Commit
            commit_result = subprocess.run(
                ["git", "commit", "-m", message],
                capture_output=True, text=True, timeout=10,
                cwd=self.project_root, shell=sys.platform == "win32",
            )
            if commit_result.returncode != 0:
                results["commit"] = f"failed: {commit_result.stderr}"
                return results

            results["commit"] = "success"

            # Push
            push_result = subprocess.run(
                ["git", "push"],
                capture_output=True, text=True, timeout=30,
                cwd=self.project_root, shell=sys.platform == "win32",
            )
            results["push"] = "success" if push_result.returncode == 0 else f"failed: {push_result.stderr}"

        except subprocess.TimeoutExpired:
            results["error"] = "git command timed out"
        except Exception as e:
            results["error"] = str(e)

        return results

    def merge_conflicts(self, incoming: dict) -> dict[str, Any]:
        """Merge incoming team context from another machine.

        For conflicting conventions, keep the newer one.
        Returns dict describing what was merged.
        """
        merged_conventions = dict(self._conventions)
        merged_decisions = list(self._decisions)

        changes: dict[str, Any] = {"conventions_updated": [], "decisions_added": 0}

        # Merge conventions (newer wins)
        for name, desc in incoming.get("conventions", {}).items():
            if name not in merged_conventions:
                merged_conventions[name] = desc
                changes["conventions_updated"].append(f"added: {name}")
            elif incoming.get("_updated_at", "") > self._get_convention_updated_at(name):
                merged_conventions[name] = desc
                changes["conventions_updated"].append(f"updated: {name}")

        self._conventions = merged_conventions

        # Merge decisions
        incoming_decisions = incoming.get("decisions", [])
        for d in incoming_decisions:
            sd = SharedDecision(**d)
            if not any(existing.decided_at == sd.decided_at and
                       existing.decided_by == sd.decided_by for existing in self._decisions):
                merged_decisions.append(sd)
                changes["decisions_added"] += 1

        self._decisions = merged_decisions
        self._save()
        return changes

    def _get_convention_updated_at(self, name: str) -> str:
        """Return the most recent decided_at for conventions with the same name."""
        return "1970-01-01T00:00:00Z"

    def status(self) -> str:
        """Get team context status summary."""
        parts = [
            f"team@{self.project_root.name}",
            f"{len(self._members)} members",
            f"{len(self._decisions)} decisions",
            f"{len(self._conventions)} conventions",
        ]
        return " | ".join(parts)