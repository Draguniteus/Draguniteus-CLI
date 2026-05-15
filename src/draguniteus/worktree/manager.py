"""Per-agent git worktree manager for isolated parallel development.

Each orchestrated sub-agent can get its own git worktree at:
  .draguniteus/worktrees/<agent_name>/

This allows agents to make commits, switch branches, and refactor
code without colliding with the main working directory.
"""
from __future__ import annotations

import subprocess
import sys
import shutil
from pathlib import Path
from typing import Optional


class WorktreeManager:
    """Manages per-agent git worktrees.

    Usage:
        mgr = WorktreeManager(project_root)
        mgr.create_worktree("explorer", base_branch="main")
        worktree_path = mgr.get_worktree("explorer")
        mgr.cleanup_worktree("explorer")
    """

    def __init__(self, project_root: Path | None = None):
        self.project_root = project_root or Path.cwd()
        self.worktrees_root = self.project_root / ".draguniteus" / "worktrees"
        self.worktrees_root.mkdir(parents=True, exist_ok=True)

    def create_worktree(self, agent_name: str, base_branch: str = "HEAD") -> Path:
        """Create a new worktree for an agent.

        Args:
            agent_name: Unique name for this agent (used as worktree dir name)
            base_branch: Branch to base the worktree on (default: current HEAD)

        Returns:
            Path to the new worktree directory

        Raises:
            RuntimeError: If git worktree creation fails
        """
        worktree_path = self.worktrees_root / agent_name

        if worktree_path.exists():
            # Already exists — clean it up first
            shutil.rmtree(worktree_path, ignore_errors=True)

        branch_name = f"agent/{agent_name}"

        try:
            # Create the worktree with a new branch
            result = subprocess.run(
                [
                    "git", "worktree", "add",
                    "--detach",
                    "--checkout",
                    "-b", branch_name,
                    str(worktree_path),
                    base_branch,
                ],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=self.project_root,
                shell=sys.platform == "win32",
            )
            if result.returncode != 0:
                raise RuntimeError(f"git worktree add failed: {result.stderr}")

            return worktree_path

        except subprocess.TimeoutExpired:
            raise RuntimeError(f"git worktree add timed out after 30s")
        except Exception as e:
            raise RuntimeError(f"Failed to create worktree: {e}")

    def get_worktree(self, agent_name: str) -> Optional[Path]:
        """Get the worktree path for an agent if it exists."""
        worktree_path = self.worktrees_root / agent_name
        if worktree_path.exists() and (worktree_path / ".git").exists():
            return worktree_path
        return None

    def list_worktrees(self) -> dict[str, Path]:
        """List all active worktrees. Returns {agent_name: path}."""
        result = {}
        if not self.worktrees_root.exists():
            return result

        for entry in self.worktrees_root.iterdir():
            if entry.is_dir() and (entry / ".git").exists():
                result[entry.name] = entry
        return result

    def cleanup_worktree(self, agent_name: str) -> bool:
        """Remove a worktree and its branch.

        Returns True if cleanup succeeded, False otherwise.
        """
        worktree_path = self.worktrees_root / agent_name
        if not worktree_path.exists():
            return True

        try:
            # Get the branch name before removing the worktree
            branch_name = f"agent/{agent_name}"

            # Remove the worktree
            result = subprocess.run(
                ["git", "worktree", "remove", "--force", str(worktree_path)],
                capture_output=True,
                text=True,
                timeout=15,
                cwd=self.project_root,
                shell=sys.platform == "win32",
            )

            # Try to delete the branch too (ignore failures — branch may not be there)
            subprocess.run(
                ["git", "branch", "-D", branch_name],
                capture_output=True,
                timeout=10,
                cwd=self.project_root,
                shell=sys.platform == "win32",
            )

            return result.returncode == 0

        except Exception:
            return False

    def prune_dead_worktrees(self) -> int:
        """Clean up any stale worktree directories.

        Returns the number of worktrees pruned.
        """
        count = 0
        for entry in self.worktrees_root.iterdir():
            if entry.is_dir() and not (entry / ".git").exists():
                shutil.rmtree(entry, ignore_errors=True)
                count += 1
        return count