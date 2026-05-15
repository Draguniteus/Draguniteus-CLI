"""Terminal-native visual diff viewer using Rich.

Parses `git diff` output and renders:
- Unified diff (default)
- Side-by-side diff
- Collapsed/expanded hunks
- Syntax highlighting

Works on Windows (no external diff tools needed beyond git).
"""
from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Iterator


@dataclass
class DiffHunk:
    """A contiguous block of changes."""
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: list[tuple[str, str | None, str | None]]  # (role, old_line, new_line)
    # role: "context", "add", "remove", "header"

    @property
    def is_add_only(self) -> bool:
        return all(r in ("add", "header") for r, _, _ in self.lines)

    @property
    def is_remove_only(self) -> bool:
        return all(r in ("remove", "header") for r, _, _ in self.lines)


@dataclass
class DiffFile:
    """A file's diff, containing multiple hunks."""
    old_path: str
    new_path: str
    is_new: bool = False
    is_deleted: bool = False
    is_binary: bool = False
    hunks: list[DiffHunk] = field(default_factory=list)
    staged: bool = False

    def total_additions(self) -> int:
        return sum(1 for h in self.hunks for r, _, new in h.lines if r == "add" and new)

    def total_deletions(self) -> int:
        return sum(1 for h in self.hunks for r, old, _ in h.lines if r == "remove" and old)


@dataclass
class DiffStats:
    """Summary statistics for a diff."""
    files_changed: int
    insertions: int
    deletions: int
    files: list[DiffFile]


def _run_git_diff(
    *args: str,
    staged: bool = False,
    file_path: str | None = None,
    ignore_whitespace: bool = False,
) -> str:
    """Run git diff and return output."""
    cmd = ["git", "diff"]
    if staged:
        cmd.append("--cached")
    if ignore_whitespace:
        cmd.append("--ignore-space-change")
    if file_path:
        cmd.append("--")
        cmd.append(file_path)
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            shell=sys.platform == "win32",
        )
        return result.stdout
    except Exception as e:
        return f"Error running git diff: {e}"


def _parse_hunk_header(line: str) -> tuple[int, int, int, int] | None:
    """Parse @@ -start,count +start,count @@ hunk header."""
    m = re.match(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", line)
    if not m:
        return None
    old_start = int(m.group(1))
    old_count = int(m.group(2)) if m.group(2) else 1
    new_start = int(m.group(3))
    new_count = int(m.group(4)) if m.group(4) else 1
    return old_start, old_count, new_start, new_count


def _parse_git_diff(output: str) -> list[DiffFile]:
    """Parse git diff output into DiffFile objects."""
    files: list[DiffFile] = []
    current_file: DiffFile | None = None
    current_hunk: DiffHunk | None = None
    old_line_num = 0
    new_line_num = 0

    for line in output.splitlines():
        # New file entry
        if line.startswith("diff --git"):
            if current_file and current_hunk:
                current_file.hunks.append(current_hunk)
            if current_file:
                files.append(current_file)
            # Parse "a/path b/path" from "diff --git a/path b/path"
            m = re.search(r"diff --git [abc]/(.+?) [abc]/(.+)$", line)
            if m:
                current_file = DiffFile(old_path=m.group(1), new_path=m.group(2))
            else:
                current_file = DiffFile(old_path="", new_path="")
            current_hunk = None

        elif line.startswith("new file"):
            if current_file:
                current_file.is_new = True

        elif line.startswith("deleted file"):
            if current_file:
                current_file.is_deleted = True

        elif line.startswith("Binary files"):
            if current_file:
                current_file.is_binary = True

        elif line.startswith("@@"):
            if current_hunk and current_file:
                current_file.hunks.append(current_hunk)
            parsed = _parse_hunk_header(line)
            if parsed:
                old_start, old_count, new_start, new_count = parsed
                current_hunk = DiffHunk(
                    old_start=old_start,
                    old_count=old_count,
                    new_start=new_start,
                    new_count=new_count,
                    lines=[],
                )
                old_line_num = old_start
                new_line_num = new_start
                if current_file is not None:
                    current_file.hunks.append(current_hunk)

        elif current_hunk is not None and line:
            role: str
            old_content: str | None = None
            new_content: str | None = None

            if line.startswith("+"):
                role = "add"
                new_content = line[1:]
                new_line_num += 1
            elif line.startswith("-"):
                role = "remove"
                old_content = line[1:]
                old_line_num += 1
            elif line.startswith(" "):
                role = "context"
                old_content = line[1:]
                new_content = line[1:]
                old_line_num += 1
                new_line_num += 1
            else:
                role = "context"
                old_content = line
                new_content = line

            current_hunk.lines.append((role, old_content, new_content))

    if current_file and current_hunk:
        current_file.hunks.append(current_hunk)
    if current_file:
        files.append(current_file)

    return files


def _get_diff_stats(files: list[DiffFile]) -> DiffStats:
    """Compute diff statistics."""
    total_add = sum(f.total_additions() for f in files)
    total_del = sum(f.total_deletions() for f in files)
    return DiffStats(
        files_changed=len(files),
        insertions=total_add,
        deletions=total_del,
        files=files,
    )


# ---------------------------------------------------------------------------
# Rich rendering
# ---------------------------------------------------------------------------

try:
    from rich.console import Console as RichConsole
    from rich.syntax import Syntax
    from rich.panel import Panel
    from rich.text import Text
    from rich.table import Table
    HAS_RICH = True
except ImportError:
    HAS_RICH = False


def _detect_language(path: str) -> str:
    """Map file extension to syntax language for highlighting."""
    ext_map = {
        ".py": "python", ".js": "javascript", ".ts": "typescript",
        ".jsx": "javascript", ".tsx": "typescript", ".go": "go",
        ".rs": "rust", ".java": "java", ".c": "c", ".cpp": "cpp",
        ".h": "cpp", ".hpp": "cpp", ".cs": "csharp", ".rb": "ruby",
        ".swift": "swift", ".kt": "kotlin", ".scala": "scala",
        ".php": "php", ".html": "html", ".css": "css", ".scss": "scss",
        ".json": "json", ".yaml": "yaml", ".yml": "yaml", ".xml": "xml",
        ".md": "markdown", ".sql": "sql", ".sh": "bash", ".bash": "bash",
        ".zsh": "bash", ".fish": "bash", ".ps1": "powershell",
        ".psm1": "powershell", ".tf": "hcl", ".dockerfile": "dockerfile",
    }
    import os.path
    _, ext = os.path.splitext(path)
    return ext_map.get(ext.lower(), "text")


class DiffViewer:
    """Renders git diffs as formatted terminal output."""

    def __init__(self, use_color: bool = True, side_by_side: bool = False,
                 collapse_unchanged: int = 3):
        self.use_color = use_color
        self.side_by_side = side_by_side
        self.collapse_unchanged = collapse_unchanged  # lines of context to show when collapsed
        self._console = None

    def _get_console(self):
        if self._console is None:
            self._console = RichConsole(force_terminal=True)
        return self._console

    def get_diff(
        self,
        file_path: str | None = None,
        staged: bool = False,
        ignore_whitespace: bool = False,
    ) -> list[DiffFile]:
        """Get diff for file(s). If file_path is None, get all changes."""
        output = _run_git_diff(
            staged=staged, file_path=file_path, ignore_whitespace=ignore_whitespace
        )
        return _parse_git_diff(output)

    def render_unified(self, files: list[DiffFile], console: "RichConsole | None" = None) -> str:
        """Render diff as unified diff using Rich with syntax highlighting."""
        if not HAS_RICH:
            return self._render_unified_plain(files)

        c = console or self._get_console()
        output_lines: list[str] = []

        stats = _get_diff_stats(files)
        stats_table = Table(show_header=False, box=None, pad_edge_cells=False)
        stats_table.add_column(style="dim")
        stats_table.add_row(f"📁 {stats.files_changed} file(s) changed", end_section=True)

        with c.capture() as capture:
            # Print summary
            c.print(f"[bold]Diff:[/bold] {stats.files_changed} files, ", end="")
            c.print(f"[green]+{stats.insertions}[/green] / ", end="")
            c.print(f"[red]-{stats.deletions}[/red]")

            for df in files:
                if df.is_binary:
                    c.print(f"\n[bold dim]Binary:[/bold dim] {df.new_path or df.old_path} (binary)")
                    continue

                lang = _detect_language(df.new_path or df.old_path)

                c.print(f"\n[bold]{df.new_path or df.old_path}[/bold]  ", end="")
                c.print(f"[green]+{df.total_additions()}[/green] / ", end="")
                c.print(f"[red]-{df.total_deletions()}[/red]")

                for hunk in df.hunks:
                    self._render_hunk_unified(hunk, lang, c)

        return capture.get()

    def _render_hunk_unified(self, hunk: DiffHunk, lang: str, c: "RichConsole") -> None:
        """Render a single hunk with optional collapse."""
        # Build unified text
        old_num = hunk.old_start
        new_num = hunk.new_start

        # Detect if we should collapse context
        context_lines = [i for i, (r, _, _) in enumerate(hunk.lines)
                         if r == "context"]
        should_collapse = (
            self.collapse_unchanged > 0 and
            len(context_lines) > self.collapse_unchanged * 2 + 2
        )

        if should_collapse:
            # Show first N context lines, skip middle, show last N
            first_ctx = self.collapse_unchanged
            last_ctx = self.collapse_unchanged
            visible_indices = set(context_lines[:first_ctx]) | set(context_lines[-last_ctx:])
            shown_lines = []
            for i, line in enumerate(hunk.lines):
                if i in visible_indices or line[0] in ("add", "remove"):
                    shown_lines.append((i, line))
            omitted_before = first_ctx
            omitted_after = last_ctx
        else:
            shown_lines = list(enumerate(hunk.lines))
            omitted_before = omitted_after = 0

        header = (f"[dim]@@ -{hunk.old_start},{hunk.old_count} "
                  f"+{hunk.new_start},{hunk.new_count} @@[/dim]")
        c.print(header)

        for idx, (role, old, new) in shown_lines:
            if role == "header":
                continue
            if old is not None and new is None:
                c.print(f"[red]-{old}[/red]")
            elif new is not None and old is None:
                c.print(f"[green]+{new}[/green]")
            else:
                c.print(f" {old or ''}")

        if omitted_before or omitted_after:
            c.print(f"[dim]  ... {omitted_before + omitted_after} unchanged lines "
                    f"collapsed ...[/dim]")

    def _render_unified_plain(self, files: list[DiffFile]) -> str:
        """Fallback plain text rendering without Rich."""
        lines: list[str] = []
        for df in files:
            lines.append(f"--- {df.old_path}")
            lines.append(f"+++ {df.new_path}")
            for hunk in df.hunks:
                lines.append(f"@@ -{hunk.old_start},{hunk.old_count} "
                             f"+{hunk.new_start},{hunk.new_count} @@")
                for role, old, new in hunk.lines:
                    if role == "add":
                        lines.append(f"+{new}")
                    elif role == "remove":
                        lines.append(f"-{old}")
                    else:
                        lines.append(f" {old or ''}")
        return "\n".join(lines)

    def render_side_by_side(self, files: list[DiffFile], console: "RichConsole | None" = None,
                             width: int | None = None) -> str:
        """Render side-by-side diff (each half = half terminal width)."""
        if not HAS_RICH:
            return self._render_unified_plain(files)

        c = console or self._get_console()
        term_width = width or (c.width or 120)
        half = max(40, (term_width - 10) // 2)

        with c.capture() as capture:
            stats = _get_diff_stats(files)
            c.print(f"[bold]Side-by-side diff:[/bold] {stats.files_changed} files, "
                    f"[green]+{stats.insertions}[/green] / [red]-{stats.deletions}[/red]\n")

            for df in files:
                if df.is_binary:
                    c.print(f"[dim]Binary:[/dim] {df.new_path or df.old_path}")
                    continue

                c.print(f"[bold]{df.new_path or df.old_path}[/bold]\n")

                for hunk in df.hunks:
                    self._render_hunk_side_by_side(hunk, half, c)

        return capture.get()

    def _render_hunk_side_by_side(self, hunk: DiffHunk, half: int, c: "RichConsole") -> None:
        """Render a single hunk in side-by-side format."""
        old_buf: list[str] = []
        new_buf: list[str] = []

        for role, old, new in hunk.lines:
            pad_width = max(len(str(hunk.old_start + hunk.old_count)),
                            len(str(hunk.new_start + hunk.new_count))) + 1
            if role == "add":
                old_buf.append(f"[red]{'': <{pad_width}}|[/red]")
                new_buf.append(f"[green]+{new}[/green]")
            elif role == "remove":
                old_buf.append(f"[red]-{old}[/red]")
                new_buf.append(f"[red]{'': <{pad_width}}|[/red]")
            elif role == "context":
                old_buf.append(f" {old or ''}")
                new_buf.append(f" {new or ''}")

        for o, n in zip(old_buf, new_buf):
            c.print(f"{o:<{half}} │ {n}")


def render_diff_to_console(
    file_path: str | None = None,
    staged: bool = False,
    side_by_side: bool = False,
    ignore_whitespace: bool = False,
    collapse_unchanged: int = 3,
) -> str:
    """One-call function to get a formatted diff string."""
    viewer = DiffViewer(collapse_unchanged=collapse_unchanged, side_by_side=side_by_side)
    files = viewer.get_diff(file_path=file_path, staged=staged, ignore_whitespace=ignore_whitespace)
    if not files:
        return "No changes found."
    if side_by_side:
        return viewer.render_side_by_side(files)
    return viewer.render_unified(files)