"""Git tools: Status, Diff, Commit, Push, PR."""
from __future__ import annotations

from typing import Any

GIT_TOOLS: list[dict[str, Any]] = [
    {
        "name": "GitStatus",
        "description": "Show the current git working tree status.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Repo path (defaults to cwd)"}
            }
        }
    },
    {
        "name": "GitDiff",
        "description": "Show unstaged changes (diff against index) or staged changes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Repo path"},
                "commit": {"type": "string", "description": "Show diff for a specific commit"},
                "staged": {"type": "boolean", "default": False, "description": "Show staged changes"}
            }
        }
    },
    {
        "name": "GitCommit",
        "description": "Create a git commit with the given message.",
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {"type": "string"},
                "files": {"type": "array", "items": {"type": "string"}, "description": "Specific files to commit (default: all staged)"}
            },
            "required": ["message"]
        }
    },
    {
        "name": "GitPush",
        "description": "Push commits to a remote.",
        "input_schema": {
            "type": "object",
            "properties": {
                "remote": {"type": "string", "default": "origin"},
                "branch": {"type": "string", "description": "Branch to push (default: current)"}
            }
        }
    },
    {
        "name": "GitPRCreate",
        "description": "Create a pull request via gh CLI.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "body": {"type": "string"},
                "head": {"type": "string", "description": "Branch head (default: current)"},
                "base": {"type": "string", "default": "main", "description": "Target branch"}
            },
            "required": ["title", "body"]
        }
    },
]


def _run_git(args: list[str], cwd: str | None = None) -> str:
    """Run a git command and return output."""
    import subprocess
    try:
        result = subprocess.run(
            ["git"] + args,
            capture_output=True,
            text=True,
            cwd=cwd or None,
        )
        return result.stdout + result.stderr
    except Exception as e:
        return f"Git error: {e}"


def tool_git_status(path: str | None = None) -> str:
    return _run_git(["status", "--short"], cwd=path)


def tool_git_diff(path: str | None = None, commit: str | None = None, staged: bool = False) -> str:
    if commit:
        return _run_git(["show", "--stat", commit], cwd=path)
    args = ["diff"] + (["--cached"] if staged else [])
    return _run_git(args, cwd=path)


def tool_git_commit(message: str, files: list[str] | None = None) -> str:
    if files:
        for f in files:
            _run_git(["add", f])
    return _run_git(["commit", "-m", message])


def tool_git_push(remote: str = "origin", branch: str | None = None) -> str:
    args = ["push", remote]
    if branch:
        args.append(branch)
    return _run_git(args)


def tool_git_pr_create(title: str, body: str, head: str | None = None, base: str = "main") -> str:
    import subprocess
    args = ["pr", "create", "-t", title, "-b", body, "-B", base]
    if head:
        args.extend(["-h", head])
    result = subprocess.run(["gh"] + args, capture_output=True, text=True)
    return result.stdout + result.stderr