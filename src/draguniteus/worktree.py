"""Worktree isolation: manage isolated git worktrees for Draguniteus sessions."""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from draguniteus.config import DEFAULT_CONFIG_DIR


class WorktreeManager:
    """Manages isolated git worktrees at .draguniteus/worktrees/<name>."""

    def __init__(self, repo_path: Path | None = None):
        self.repo_path = repo_path or Path.cwd()
        self.worktrees_base = self.repo_path / ".draguniteus" / "worktrees"
        self.worktrees_base.mkdir(parents=True, exist_ok=True)

    def create(self, name: str, branch_from: str | None = None) -> tuple[bool, str]:
        """Create a new worktree. Returns (success, message)."""
        worktree_path = self.worktrees_base / name

        if worktree_path.exists():
            return False, f"Worktree '{name}' already exists at {worktree_path}"

        # Check if we're in a git repo
        if not (self.repo_path / ".git").exists():
            return False, "Not in a git repository. Worktree requires git."

        try:
            # Create worktree
            cmd = ["git", "worktree", "add", str(worktree_path)]
            if branch_from:
                cmd.extend(["-b", f"worktree/{name}", branch_from])
            else:
                # Use current branch
                result = subprocess.run(
                    ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                    cwd=self.repo_path,
                    capture_output=True,
                    text=True,
                )
                current_branch = result.stdout.strip()
                cmd.append(current_branch)

            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                return False, f"Failed to create worktree: {result.stderr}"

            return True, f"Worktree created at {worktree_path}"

        except Exception as e:
            return False, f"Error creating worktree: {e}"

    def list(self) -> list[dict[str, Any]]:
        """List all worktrees."""
        worktrees = []
        if not self.worktrees_base.exists():
            return worktrees

        for wt in self.worktrees_base.iterdir():
            if wt.is_dir():
                # Check git worktree metadata
                head_file = wt / ".git"
                is_worktree = False
                branch = "unknown"
                if head_file.is_file():
                    # Read gitdir reference
                    try:
                        gitdir_ref = head_file.read_text().strip()
                        if gitdir_ref.startswith("gitdir:"):
                            is_worktree = True
                    except Exception:
                        pass

                worktrees.append({
                    "name": wt.name,
                    "path": str(wt),
                    "active": is_worktree,
                })

        return worktrees

    def remove(self, name: str) -> tuple[bool, str]:
        """Remove a worktree."""
        worktree_path = self.worktrees_base / name

        if not worktree_path.exists():
            return False, f"Worktree '{name}' not found"

        try:
            # Remove worktree
            result = subprocess.run(
                ["git", "worktree", "remove", str(worktree_path)],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                return False, f"Failed to remove worktree: {result.stderr}"

            return True, f"Worktree '{name}' removed"
        except Exception as e:
            return False, f"Error removing worktree: {e}"

    def get_path(self, name: str) -> Path:
        """Get the path for a worktree by name."""
        return self.worktrees_base / name