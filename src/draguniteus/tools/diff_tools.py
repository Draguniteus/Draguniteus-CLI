"""Diff tools — git diff wrappers for tool use."""
from __future__ import annotations

from typing import Any


DIFF_TOOLS: list[dict[str, Any]] = [
    {
        "name": "tool_diff",
        "description": "Show uncommitted changes across all files as a formatted diff. Uses git diff to show what has changed.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file": {
                    "type": "string",
                    "description": "Specific file to diff (default: all files)"
                },
                "staged": {
                    "type": "boolean",
                    "default": False,
                    "description": "Show staged changes (git diff --cached)"
                },
                "side_by_side": {
                    "type": "boolean",
                    "default": False,
                    "description": "Show side-by-side diff (default: unified)"
                },
                "ignore_whitespace": {
                    "type": "boolean",
                    "default": False,
                    "description": "Ignore whitespace when computing diffs"
                }
            }
        }
    },
    {
        "name": "tool_diff_staged",
        "description": "Show staged changes — files that have been added but not yet committed.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file": {
                    "type": "string",
                    "description": "Specific staged file to diff"
                }
            }
        }
    },
]


def tool_diff(
    file: str | None = None,
    staged: bool = False,
    side_by_side: bool = False,
    ignore_whitespace: bool = False,
    **kwargs,
) -> str:
    """Show formatted diff of uncommitted changes."""
    try:
        from draguniteus.diff.viewer import DiffViewer

        viewer = DiffViewer(collapse_unchanged=3, side_by_side=side_by_side)
        files = viewer.get_diff(file_path=file, staged=staged, ignore_whitespace=ignore_whitespace)

        if not files:
            return "No changes found."

        scope = "staged" if staged else "uncommitted"
        prefix = f"## Git Diff ({scope})"
        if file:
            prefix += f" — {file}"

        if side_by_side:
            return prefix + "\n" + viewer.render_side_by_side(files)
        return prefix + "\n" + viewer.render_unified(files)
    except Exception as e:
        return f"Diff error: {e}"


def tool_diff_staged(file: str | None = None, **kwargs) -> str:
    """Show diff of staged changes."""
    return tool_diff(file=file, staged=True, side_by_side=False, **kwargs)