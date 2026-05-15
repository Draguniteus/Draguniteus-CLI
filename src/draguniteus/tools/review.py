"""Autonomous code review tools: continuous background analysis."""
from __future__ import annotations

import threading
import time
from typing import Any


REVIEW_TOOLS = [
    {
        "name": "StartCodeReview",
        "description": "Start a continuous background code review agent that monitors file changes and proactively identifies issues. Runs in background.",
        "input_schema": {
            "type": "object",
            "properties": {
                "paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Files or directories to monitor"
                },
                "severity": {
                    "type": "string",
                    "enum": ["all", "high_only"],
                    "default": "all",
                    "description": "Only report high severity issues"
                },
                "extensions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": [".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java", ".c", ".cpp", ".h"],
                    "description": "File extensions to monitor (include leading dot)"
                }
            },
            "required": ["paths"]
        }
    },
    {
        "name": "StopCodeReview",
        "description": "Stop the background code review agent.",
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "GetReviewFindings",
        "description": "Get current findings from the background code review agent.",
        "input_schema": {
            "type": "object",
            "properties": {
                "since": {"type": "string", "description": "ISO timestamp to filter from"},
                "severity": {"type": "string", "enum": ["all", "high", "medium", "low"], "default": "all", "description": "Filter by severity"},
                "file": {"type": "string", "description": "Filter findings for a specific file"}
            }
        }
    }
]


# Background review state
_review_agent = None
_review_thread: threading.Thread | None = None
_review_findings: list[dict] = []
_review_findings_lock = threading.Lock()


IGNORE_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv",
               ".idea", ".vscode", "dist", "build", ".tox", ".pytest_cache",
               "vendor", "target", "pkg", ".node_modules", "bower_components"}


def _matches_extension(path: str, extensions: list[str]) -> bool:
    return any(path.endswith(ext) for ext in extensions)


class BackgroundReviewAgent:
    """Continuous background code review."""

    def __init__(self, paths: list[str], severity: str = "all",
                 extensions: list[str] | None = None):
        self.paths = paths
        self.severity = severity
        self.extensions = extensions or [".py", ".js", ".ts", ".tsx", ".jsx",
                                         ".go", ".rs", ".java", ".c", ".cpp", ".h"]
        self._running = False
        self._last_mtimes: dict[str, float] = {}
        self._findings_by_file: dict[str, set[tuple[str, str]]] = {}  # dedup

    def start(self) -> None:
        self._running = True
        t = threading.Thread(target=self._run, daemon=True)
        t.start()

    def stop(self) -> None:
        self._running = False

    def _run(self) -> None:
        global _review_findings
        import time

        # Initial scan
        self._scan_all()

        while self._running:
            time.sleep(10)  # Check every 10 seconds
            self._scan_changes()

    def _scan_all(self) -> None:
        """Full scan of all paths."""
        from pathlib import Path
        for path_str in self.paths:
            path = Path(path_str)
            if path.is_file():
                if _matches_extension(str(path), self.extensions):
                    self._review_file(path)
            elif path.is_dir():
                for f in path.rglob("*"):
                    if f.is_file() and _matches_extension(str(f), self.extensions):
                        if not any(ignored in str(f) for ignored in IGNORE_DIRS):
                            self._review_file(f)

    def _scan_changes(self) -> None:
        """Scan only changed files."""
        from pathlib import Path
        import time

        for path_str in self.paths:
            path = Path(path_str)
            if path.is_file():
                mtime = path.stat().st_mtime
                if self._last_mtimes.get(str(path)) != mtime:
                    self._last_mtimes[str(path)] = mtime
                    if _matches_extension(str(path), self.extensions):
                        self._review_file(path)
            elif path.is_dir():
                for f in path.rglob("*"):
                    if not f.is_file():
                        continue
                    if not _matches_extension(str(f), self.extensions):
                        continue
                    if any(ignored in str(f) for ignored in IGNORE_DIRS):
                        continue
                    mtime = f.stat().st_mtime
                    if self._last_mtimes.get(str(f)) != mtime:
                        self._last_mtimes[str(f)] = mtime
                        self._review_file(f)

    def _review_file(self, path: "Path") -> None:
        """Review a single file."""
        global _review_findings

        try:
            content = path.read_text(errors="ignore")
        except Exception:
            return

        findings = []
        file_key = str(path)
        seen = self._findings_by_file.setdefault(file_key, set())

        # Security checks
        if self._check_secrets(content):
            key = ("security", "Possible secret/key detected in code")
            if key not in seen:
                seen.add(key)
                findings.append({
                    "severity": "high",
                    "type": "security",
                    "file": str(path),
                    "message": "Possible secret/key detected in code",
                })
        if "eval(" in content:
            key = ("security", "Use of eval() is a security risk")
            if key not in seen:
                seen.add(key)
                findings.append({
                    "severity": "high",
                    "type": "security",
                    "file": str(path),
                    "message": "Use of eval() is a security risk",
                })
        if "pickle.loads" in content:
            key = ("security", "pickle.loads can execute arbitrary code")
            if key not in seen:
                seen.add(key)
                findings.append({
                    "severity": "high",
                    "type": "security",
                    "file": str(path),
                    "message": "pickle.loads can execute arbitrary code",
                })

        # Performance checks
        if content.count("SELECT") > 5 and "for " in content:
            key = ("performance", "Possible N+1 query pattern detected")
            if key not in seen:
                seen.add(key)
                findings.append({
                    "severity": "medium",
                    "type": "performance",
                    "file": str(path),
                    "message": "Possible N+1 query pattern detected",
                })
        if ".append(" in content and "for " in content:
            key = ("performance", "Consider list comprehension for append loop")
            if key not in seen:
                seen.add(key)
                findings.append({
                    "severity": "low",
                    "type": "performance",
                    "file": str(path),
                    "message": "Consider list comprehension for append loop",
                })

        # Correctness checks
        if "except:" in content and "pass" in content:
            key = ("correctness", "Bare except: with pass swallows all errors")
            if key not in seen:
                seen.add(key)
                findings.append({
                    "severity": "medium",
                    "type": "correctness",
                    "file": str(path),
                    "message": "Bare except: with pass swallows all errors",
                })
        if "TODO" in content or "FIXME" in content:
            key = ("maintainability", "TODO/FIXME comment found")
            if key not in seen:
                seen.add(key)
                findings.append({
                    "severity": "low",
                    "type": "maintainability",
                    "file": str(path),
                    "message": "TODO/FIXME comment found",
                })

        # Filter by severity if needed
        if self.severity == "high_only":
            findings = [f for f in findings if f["severity"] == "high"]

        if findings:
            with _review_findings_lock:
                _review_findings.extend(findings)

    def _check_secrets(self, content: str) -> bool:
        """Check for potential secrets."""
        import re
        patterns = [
            r'api[_-]?key["\']?\s*[:=]\s*["\'][A-Za-z0-9]{20,}',
            r'secret["\']?\s*[:=]\s*["\'][A-Za-z0-9]{20,}',
            r'password["\']?\s*[:=]\s*["\'][^"\']+',
            r'-----BEGIN.*PRIVATE KEY-----',
        ]
        return any(re.search(p, content) for p in patterns)


def tool_start_code_review(paths: list[str], severity: str = "all",
                           extensions: list[str] | None = None, **kwargs) -> str:
    """Start background code review."""
    global _review_agent, _review_thread, _review_findings

    if _review_agent is not None and _review_agent._running:
        return "Code review already running. Use StopCodeReview first."

    _review_findings = []
    _review_agent = BackgroundReviewAgent(paths, severity, extensions)
    _review_agent.start()

    ext_str = ",".join(extensions or [".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java", ".c", ".cpp", ".h"])
    return (f"Started background code review on {len(paths)} paths, "
            f"extensions [{ext_str}]. Use GetReviewFindings to see issues, "
            f"StopCodeReview to stop.")


def tool_stop_code_review(**kwargs) -> str:
    """Stop background code review."""
    global _review_agent

    if _review_agent is None:
        return "No code review running."

    _review_agent.stop()
    _review_agent = None

    count = len(_review_findings)
    return f"Stopped code review. {count} total findings accumulated."


def tool_get_review_findings(since: str | None = None,
                              severity: str = "all",
                              file: str | None = None,
                              **kwargs) -> str:
    """Get current review findings with optional filtering."""
    global _review_findings

    if _review_agent is None:
        return "No code review running."

    with _review_findings_lock:
        findings = list(_review_findings)

    if not findings:
        return "No findings yet."

    # Filter by severity
    if severity and severity != "all":
        findings = [f for f in findings if f.get("severity") == severity]

    # Filter by file
    if file:
        findings = [f for f in findings if file in f.get("file", "")]

    # Filter by timestamp if provided
    if since:
        import datetime
        try:
            cutoff = datetime.fromisoformat(since.replace("Z", "+00:00"))
            findings = [f for f in findings if f.get("timestamp", "") > since]
        except Exception:
            pass

    if not findings:
        return f"No findings matching filters (severity={severity}, file={file})."

    lines = [f"## Code Review Findings ({len(findings)} total)\n"]
    by_file: dict[str, list] = {}
    for f in findings:
        by_file.setdefault(f["file"], []).append(f)

    for file_path, file_findings in by_file.items():
        lines.append(f"### {file_path}")
        for finding in file_findings:
            sev = finding["severity"]
            marker = "🔴" if sev == "high" else "🟡" if sev == "medium" else "⚪"
            lines.append(f"  {marker} [{sev}] {finding['type']}: {finding['message']}")
        lines.append("")

    return "\n".join(lines)
