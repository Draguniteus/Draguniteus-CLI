"""PR review status integration: detect open PR and show colored status."""
from __future__ import annotations

import subprocess
from typing import Any


class PRStatusChecker:
    """Check PR status using gh CLI."""

    PR_COLORS = {
        "approved": "green",
        "pending": "yellow",
        "changes_requested": "red",
        "draft": "gray",
        "merged": "purple",
    }

    def __init__(self):
        self._gh_available: bool | None = None

    def is_gh_available(self) -> bool:
        """Check if gh CLI is installed and authenticated."""
        if self._gh_available is not None:
            return self._gh_available
        try:
            result = subprocess.run(
                ["gh", "auth", "status"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            self._gh_available = result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            self._gh_available = False
        return self._gh_available

    def get_current_branch(self) -> str | None:
        """Get current git branch."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return None

    def get_pr_for_branch(self, branch: str) -> dict[str, Any] | None:
        """Get PR info for current branch."""
        if not self.is_gh_available():
            return None

        try:
            # Get PR for current branch
            result = subprocess.run(
                ["gh", "pr", "view", branch, "--json", "number,title,state,url,reviewDecision"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                import json
                return json.loads(result.stdout)
        except Exception:
            pass
        return None

    def get_pr_status_display(self) -> str | None:
        """Get a colored PR status display string."""
        branch = self.get_current_branch()
        if not branch:
            return None

        pr = self.get_pr_for_branch(branch)
        if not pr:
            return None

        pr_number = pr.get("number", "?")
        pr_url = pr.get("url", "")
        pr_state = pr.get("state", "unknown").lower()
        review_decision = pr.get("reviewDecision", "").lower()

        # Determine color based on review decision
        if review_decision == "approved":
            color = "green"
            status_text = "approved"
        elif review_decision == "changes_requested":
            color = "red"
            status_text = "changes requested"
        elif review_decision == "pending" or review_decision == "review_required":
            color = "yellow"
            status_text = "pending review"
        elif pr_state == "merged":
            color = "purple"
            status_text = "merged"
        elif pr_state == "draft":
            color = "gray"
            status_text = "draft"
        else:
            color = "gray"
            status_text = pr_state

        return f"PR #{pr_number} ({status_text})"


# Global instance
pr_status = PRStatusChecker()