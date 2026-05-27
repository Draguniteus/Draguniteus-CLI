"""Shell tool: Bash execution with permission gating."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

# Tool schemas
SHELL_TOOLS: list[dict[str, Any]] = [
    {
        "name": "Bash",
        "description": "Execute a shell command in the user's environment. " +
                       "Returns stdout + stderr combined. Use for builds, tests, git, etc.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string"},
                "description": {"type": "string", "description": "Why this command is needed"},
                "timeout": {"type": "integer", "default": 60},
                "working_dir": {"type": "string"}
            },
            "required": ["command"]
        }
    },
]


MAX_BASH_OUTPUT = 100 * 1024  # 100 KB — truncate bash output beyond this


def tool_bash(
    command: str,
    description: str | None = None,
    timeout: int = 60,
    working_dir: str | None = None,
) -> str:
    """Execute a shell command and return stdout+stderr."""
    # Check permissions before execution
    # Import from cli to use the shared permission store with permission_mode
    from draguniteus import cli
    perms = cli._get_permissions() if hasattr(cli, '_get_permissions') else None

    if perms is None:
        # Fallback if cli not initialized properly
        from draguniteus.permissions import PermissionStore
        from draguniteus.config import Config
        try:
            perms = PermissionStore(Config())
        except Exception:
            perms = None

    if perms:
        check = perms.check("Bash", command)
        if check in ("deny", "block"):
            return f"[Permission denied] Command matches a deny pattern."
        if check == "ask":
            # Auto-approve in non-interactive/CI mode, when stdin is not a TTY,
            # when questionary can't prompt (NoConsoleScreenBufferError in Git Bash),
            # or when permission mode is dontAsk/bypassPermissions.
            # Default to "y" (auto-approve) since this is a CLI coding agent —
            # user is present and can interrupt if something goes wrong.
            permission_mode = getattr(cli, '_permission_mode', 'default') if hasattr(cli, '_permission_mode') else 'default'
            if os.environ.get("DRAGUNITEUS_NONINTERACTIVE") == "1":
                pass  # auto-approve
            elif permission_mode in ("dontAsk", "bypassPermissions"):
                pass  # auto-approve
            elif not sys.stdin.isatty():
                pass  # auto-approve (pipe/heredoc mode)
            else:
                # Interactive mode — prompt user, default to approve if prompt fails
                response = "y"
                try:
                    from draguniteus import theming
                    response = theming.print_permission_prompt("Bash", command, full_drama=True)
                except Exception:
                    # questionary/prompt failed on Windows conhost — auto-approve
                    response = "y"

                if response == "a":
                    # Save permanent rule for this project + command pattern
                    perms.add_rule("Bash", command, "auto_approve")
                    perms.save()
                    response = "y"
                if response != "y":
                    return f"[Permission denied] User denied: {command[:50]}..."
                if response == "y":
                    perms.remember_approval("Bash", command)

    cwd = Path(working_dir).expanduser() if working_dir else Path.cwd()
    # Normalize Windows Git Bash paths
    if os.name == "nt":
        cwd_str = str(cwd)
        if cwd_str.startswith("\\c\\") or cwd_str.startswith("/c/"):
            cwd = Path("C:/" + cwd_str[3:].replace("/", "/"))

    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = result.stdout + result.stderr
        # Truncate large output to prevent memory issues and token bloat
        if len(output) > MAX_BASH_OUTPUT:
            output = output[:MAX_BASH_OUTPUT] + f"\n[...output truncated to {MAX_BASH_OUTPUT // 1024}KB...]"
        if result.returncode != 0:
            return f"[exit {result.returncode}]\n{output}"
        return output if output else "ok"
    except subprocess.TimeoutExpired:
        return f"Error: Command timed out after {timeout}s"
    except Exception as e:
        return f"Error executing command: {e}"