"""Shell tool: Bash execution with permission gating."""
from __future__ import annotations

import os
import subprocess
import sys
import time
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
MAX_LINES_TO_SHOW = 500  # for streaming display of long output
STREAMING_THRESHOLD = 20 * 1024  # stream output live when >20KB expected

# Error categories for better classification
TRANSIENT_ERRORS = frozenset([
    "timeout", "timed out", "connection refused", "temporarily unavailable",
    "rate limit", "too many requests", "server busy", "try again",
    "503", "502", "429", "ECONNRESET", "ETIMEDOUT", "no such file or directory",
])
PERMANENT_ERRORS = frozenset([
    "not found", "invalid", "not permitted", "permission denied",
    "does not exist", "unauthorized", "forbidden", "400", "401", "403", "404",
    "syntax error", "cannot execute", "operation not permitted",
])


def tool_bash(
    command: str,
    description: str | None = None,
    timeout: int = 60,
    working_dir: str | None = None,
) -> str:
    """Execute a shell command and return stdout+stderr.

    Large outputs are streamed in real-time to avoid buffering delays.
    Error classification enables better retry hints in the agent.
    """
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

    # Classify command type for output handling
    cmd_lower = command.lower().strip()
    is_build = any(k in cmd_lower for k in ["pip install", "npm install", "cargo build", "make", "pytest", "python -m"])
    is_streaming = is_build or any(k in cmd_lower for k in ["tail -f", "watch", "log", "stream"])

    try:
        # Use Popen for streaming-capable execution
        proc = subprocess.Popen(
            command,
            shell=True,
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        # Read stdout and stderr in streaming fashion for large output
        stdout_chunks = []
        stderr_chunks = []
        line_count = 0
        start_time = time.time()

        # Read in non-blocking manner using threads for stdout/stderr
        import threading

        def read_stream(stream, chunks, is_stderr=False):
            try:
                for line in stream:
                    if line is not None:
                        chunks.append(line)
            except Exception:
                pass

        stdout_thread = threading.Thread(target=read_stream, args=(proc.stdout, stdout_chunks))
        stderr_thread = threading.Thread(target=read_stream, args=(proc.stderr, stderr_chunks))
        stdout_thread.start()
        stderr_thread.start()

        # Wait with timeout
        try:
            proc.wait(timeout=timeout)
            stdout_thread.join(timeout=2)
            stderr_thread.join(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            return f"Error: Command timed out after {timeout}s"

        elapsed = time.time() - start_time
        combined = stdout_chunks + stderr_chunks

        # Streaming display for build/test commands
        if is_streaming and len(combined) > 5:
            try:
                sys.stdout.buffer.write(f"\n  {theming.CYAN}--- output ({len(combined)} lines, {elapsed:.1f}s) ---{theming.RESET}\n".encode('utf-8', errors='replace'))
                sys.stdout.buffer.flush()
                for i, line in enumerate(combined[:MAX_LINES_TO_SHOW]):
                    prefix = "" if i > 0 else "  "
                    try:
                        sys.stdout.buffer.write(f"{prefix}{line}".encode('utf-8', errors='replace'))
                        sys.stdout.buffer.flush()
                    except Exception:
                        pass
                if len(combined) > MAX_LINES_TO_SHOW:
                    try:
                        sys.stdout.buffer.write(f"\n  {theming.DIM}... ({len(combined) - MAX_LINES_TO_SHOW} more lines) ...{theming.RESET}\n".encode('utf-8', errors='replace'))
                        sys.stdout.buffer.flush()
                    except Exception:
                        pass
                sys.stdout.buffer.write(f"  {theming.CYAN}--- end ---{theming.RESET}\n".encode('utf-8', errors='replace'))
                sys.stdout.buffer.flush()
            except Exception:
                pass

        output = "".join(combined)
        # Truncate large output to prevent memory issues and token bloat
        if len(output) > MAX_BASH_OUTPUT:
            output = output[:MAX_BASH_OUTPUT] + f"\n[...output truncated to {MAX_BASH_OUTPUT // 1024}KB...]"

        returncode = proc.returncode
        if returncode != 0:
            # Classify error type
            err_type = "transient" if any(e in output.lower() for e in TRANSIENT_ERRORS) else "permanent"
            return f"[exit {returncode}] [{err_type}]\n{output}"
        return output if output else "ok"

    except Exception as e:
        return f"Error executing command: {e}"