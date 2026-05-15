"""Filesystem tools: Read, Write, Edit, Glob, Grep."""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

# Tool schemas in Anthropic function-calling format
FILESYSTEM_TOOLS: list[dict[str, Any]] = [
    {
        "name": "Read",
        "description": "Read the complete contents of one or more files. " +
                       "Use this to understand code, view data, or inspect configurations.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Absolute or relative path to the file to read."
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of lines to read (from the start)."
                },
                "offset": {
                    "type": "integer",
                    "description": "Line offset to start reading from (0-indexed)."
                }
            },
            "required": ["file_path"]
        }
    },
    {
        "name": "Write",
        "description": "Create a new file or overwrite an existing file with the provided content. " +
                       "Use for new files, refactoring, or applying multi-file changes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the file to create or overwrite."
                },
                "content": {
                    "type": "string",
                    "description": "Full file content to write."
                },
                "description": {
                    "type": "string",
                    "description": "Optional reason for writing this file."
                }
            },
            "required": ["file_path", "content"]
        }
    },
    {
        "name": "Edit",
        "description": "Make a targeted edit to an existing file using a search-replace pair. " +
                       "Use for single-target changes, bug fixes, or adding code to files.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the file to edit."
                },
                "old_string": {
                    "type": "string",
                    "description": "The exact text in the file to replace. Must match exactly."
                },
                "new_string": {
                    "type": "string",
                    "description": "The new text to replace the old_string with."
                }
            },
            "required": ["file_path", "old_string", "new_string"]
        }
    },
    {
        "name": "Glob",
        "description": "Recursively find all files matching a glob pattern. " +
                       "Use to discover project structure, find all test files, etc.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern (e.g., '**/*.py', 'src/**/*.ts')."
                },
                "path": {
                    "type": "string",
                    "description": "Root directory to search from. Defaults to cwd."
                }
            },
            "required": ["pattern"]
        }
    },
    {
        "name": "Grep",
        "description": "Search for a regex pattern in files. Returns matching lines with context.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory or file path to search in."
                },
                "pattern": {
                    "type": "string",
                    "description": "Regex pattern to search for."
                },
                "output_mode": {
                    "type": "string",
                    "enum": ["content", "files_with_matches", "count"],
                    "default": "content"
                },
                "glob": {
                    "type": "string",
                    "description": "Filter to files matching this glob pattern."
                },
                "context": {
                    "type": "integer",
                    "default": 2,
                    "description": "Number of lines of context before/after match."
                }
            },
            "required": ["path", "pattern"]
        }
    },
    {
        "name": "Bash",
        "description": "Execute a shell command. Returns stdout + stderr. " +
                       "Use for running tests, builds, git commands, linters, etc.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute."
                },
                "description": {
                    "type": "string",
                    "description": "Human-readable explanation of why this command is needed."
                },
                "timeout": {
                    "type": "integer",
                    "default": 60,
                    "description": "Timeout in seconds."
                },
                "working_dir": {
                    "type": "string",
                    "description": "Directory to run the command in."
                }
            },
            "required": ["command"]
        }
    },
]


# ------------------------------------------------------------------
# Tool implementations
# ------------------------------------------------------------------

def tool_read(file_path: str, limit: int | None = None, offset: int | None = None) -> str:
    """Read a file and return its contents."""
    path = _normalize_path(file_path)
    if not path.exists():
        return f"Error: File not found: {file_path}"

    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except Exception as e:
        return f"Error reading {file_path}: {e}"

    lines = content.split("\n")
    start = offset or 0
    end = limit + start if limit else None
    selected = lines[start:end]
    result = "\n".join(selected)

    suffix = ""
    if limit and len(lines) > limit:
        suffix = f"\n... (+ {len(lines) - limit} more lines)"
    if offset:
        suffix = f"\n... (lines 0-{offset} skipped)"
    return result + suffix


def _normalize_path(file_path: str) -> Path:
    """Normalize Windows Git Bash paths (/c/...) to proper Windows paths."""
    path = Path(file_path).expanduser()
    # On Windows, convert /c/ style paths from Git Bash to C:\ style
    if os.name == "nt":
        path_str = str(path)
        if path_str.startswith("\\c\\") or path_str.startswith("/c/"):
            # /c/Users/... -> C:\Users\...
            normalized = "C:\\" + path_str[3:].replace("/", "\\")
            path = Path(normalized)
    return path


def tool_write(file_path: str, content: str, description: str | None = None) -> str:
    """Write content to a file."""
    path = _normalize_path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"ok — wrote {len(content)} chars to {file_path}"
    except Exception as e:
        return f"Error writing {file_path}: {e}"


def tool_edit(file_path: str, old_string: str, new_string: str) -> str:
    """Make a targeted edit using search-replace."""
    path = _normalize_path(file_path)
    if not path.exists():
        return f"Error: File not found: {file_path}"

    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            original = f.read()
    except Exception as e:
        return f"Error reading {file_path}: {e}"

    if old_string not in original:
        return f"Error: old_string not found in {file_path}. Check for whitespace/newline mismatches."

    new_content = original.replace(old_string, new_string, 1)

    with open(path, "w", encoding="utf-8") as f:
        f.write(new_content)

    return f"ok — edited {file_path}"


def tool_glob(pattern: str, path: str | None = None) -> str:
    """Find files matching a glob pattern."""
    import glob as glob_module

    root = _normalize_path(path) if path else Path.cwd()
    # glob expects pattern relative to cwd — convert to full pattern
    full_pattern = str(root / pattern)

    try:
        matches = glob_module.glob(full_pattern, recursive=True)
        if not matches:
            return f"No files found matching {pattern}"
        return "\n".join(sorted(matches))
    except Exception as e:
        return f"Error globbing {pattern}: {e}"


def tool_grep(
    path: str,
    pattern: str,
    output_mode: str = "content",
    glob: str | None = None,
    context: int = 2
) -> str:
    """Search for regex pattern in files."""
    import re

    search_path = _normalize_path(path)
    if not search_path.exists():
        return f"Error: Path not found: {path}"

    try:
        regex = re.compile(pattern)
    except re.error as e:
        return f"Invalid regex pattern: {e}"

    results = []
    file_paths = [search_path] if search_path.is_file() else []

    if glob and search_path.is_dir():
        # Use glob to narrow files
        for g in glob.split(","):
            file_paths.extend(search_path.rglob(g.strip()))

    if not file_paths:
        file_paths = [search_path] if search_path.is_file() else []

    if search_path.is_dir():
        file_paths = list(search_path.rglob(glob or "*"))

    for fp in file_paths:
        if not fp.is_file():
            continue
        try:
            with open(fp, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            for i, line in enumerate(lines):
                if regex.search(line):
                    if output_mode == "count":
                        results.append(f"{fp}: {len([l for l in lines if regex.search(l)])} matches")
                        break
                    else:
                        ctx_before = max(0, i - context)
                        ctx_after = min(len(lines) - 1, i + context)
                        snippet = lines[ctx_before:ctx_after + 1]
                        snippet_text = "".join(snippet).strip()
                        rel_path = fp.relative_to(search_path) if search_path.is_dir() else fp.name
                        results.append(f"{rel_path}:{i + 1}: {snippet_text}")
        except Exception:
            continue

    if not results:
        return f"No matches found for '{pattern}'"

    if output_mode == "files_with_matches":
        unique = sorted(set(r.split(":")[0] for r in results))
        return "\n".join(unique)

    return "\n".join(results[:200])  # cap output