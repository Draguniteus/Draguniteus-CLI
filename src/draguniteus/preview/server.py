"""Interactive preview server — serves generated artifacts locally.

Uses Python's built-in http.server to avoid external dependencies.
Serves HTML, Markdown, images, and other previewable file types.
Auto-opens browser on first preview.
"""
from __future__ import annotations

import json
import os
import platform
import socket
import tempfile
import threading
import webbrowser
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from typing import Any

from draguniteus.theming import CYAN, DIM, GREEN, RESET


def _get_preview_dir() -> Path:
    """Get the temp directory for previews."""
    return Path(tempfile.gettempdir()) / "draguniteus_preview"


class PreviewRouter:
    """Routes requests and detects content types for preview."""

    PREVIEWABLE = frozenset([
        ".html", ".htm",
        ".md", ".markdown",
        ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp",
        ".css", ".js", ".mjs",
        ".json", ".xml",
        ".pdf",
    ])

    MARKDOWN_EXTENSIONS = frozenset([".md", ".markdown"])

    def __init__(self, preview_dir: Path | None = None):
        self.preview_dir = preview_dir or _get_preview_dir()
        self.preview_dir.mkdir(parents=True, exist_ok=True)

    def can_preview(self, path: Path) -> bool:
        """Check if a file can be previewed."""
        return path.suffix.lower() in self.PREVIEWABLE

    def get_content_type(self, path: Path) -> str:
        """Get MIME content type for a file."""
        ext = path.suffix.lower()
        types = {
            ".html": "text/html; charset=utf-8",
            ".htm": "text/html; charset=utf-8",
            ".md": "text/markdown; charset=utf-8",
            ".markdown": "text/markdown; charset=utf-8",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".svg": "image/svg+xml",
            ".webp": "image/webp",
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".mjs": "application/javascript; charset=utf-8",
            ".json": "application/json; charset=utf-8",
            ".xml": "application/xml; charset=utf-8",
            ".pdf": "application/pdf",
        }
        return types.get(ext, "application/octet-stream")

    def render_markdown(self, content: bytes) -> bytes:
        """Convert markdown to HTML using the built-in markdown module."""
        try:
            import markdown
            text = content.decode("utf-8", errors="replace")
            html = markdown.markdown(
                text,
                extensions=["tables", "fenced_code", "codehilite"],
            )
            wrapper = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
        max-width: 800px; margin: 40px auto; padding: 0 20px;
        line-height: 1.6; }}
pre {{ background: #f4f4f4; padding: 16px; overflow-x: auto; border-radius: 6px; }}
code {{ background: #f4f4f4; padding: 2px 6px; border-radius: 3px; }}
table {{ border-collapse: collapse; width: 100%; }}
td, th {{ border: 1px solid #ddd; padding: 8px; }}
</style>
</head>
<body>
{html}
</body>
</html>"""
            return wrapper.encode("utf-8")
        except Exception:
            return content

    def preview_path(self, file_path: Path | str) -> Path | None:
        """Copy or resolve a file to the preview directory."""
        src = Path(file_path) if isinstance(file_path, str) else file_path
        if not src.exists():
            return None

        # Generate safe filename
        stem = src.stem[:50]
        suffix = src.suffix
        counter = 1
        dest_name = f"{stem}{suffix}"
        dest = self.preview_dir / dest_name

        while dest.exists() and dest.stat().st_size != src.stat().st_size:
            counter += 1
            dest_name = f"{stem}_{counter}{suffix}"
            dest = self.preview_dir / dest_name
            if counter > 100:
                break

        import shutil
        shutil.copy2(src, dest)
        return dest


class PreviewHandler(SimpleHTTPRequestHandler):
    """HTTP handler for preview server with routing logic."""

    router: PreviewRouter | None = None

    def do_GET(self) -> None:
        if not self.router:
            self.send_error(500, "Router not configured")
            return

        path = self.path.strip("/")
        if not path or path == "index" or path == "/":
            self.serve_index()
            return

        # Map /<filename) to actual file in preview_dir
        file_path = self.router.preview_dir / path
        if not file_path.exists():
            self.send_error(404, f"File not found: {path}")
            return

        # Render markdown specially
        if file_path.suffix.lower() in PreviewRouter.MARKDOWN_EXTENSIONS:
            content = file_path.read_bytes()
            rendered = self.router.render_markdown(content)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", len(rendered))
            self.end_headers()
            self.wfile.write(rendered)
            return

        # Serve static file
        return super().do_GET()

    def serve_index(self) -> None:
        """Serve index of available previews."""
        if not self.router:
            return

        files = sorted(self.router.preview_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
        links = []
        for f in files[:50]:
            size = f.stat().st_size
            size_str = f"{size/1024:.1f}KB" if size > 1024 else f"{size}B"
            links.append(f'<li><a href="{f.name}">{f.name}</a> <span>({size_str})</span></li>')

        html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>Draguniteus Previews</title>
<style>
body {{ font-family: -apple-system, sans-serif; max-width: 800px; margin: 40px auto; padding: 0 20px; }}
h1 {{ color: #bd93f9; }}
ul {{ list-style: none; padding: 0; }}
li {{ padding: 8px 0; border-bottom: 1px solid #eee; }}
a {{ color: #0066cc; text-decoration: none; }}
a:hover {{ text-decoration: underline; }}
span {{ color: #888; font-size: 0.85em; }}
</style>
</head>
<body>
<h1>Draguniteus Previews</h1>
<p>Available artifacts:</p>
<ul>
{chr(10).join(links) if links else '<li>No previews yet — write an HTML or Markdown file and use /preview</li>'}
</ul>
</body>
</html>"""
        html_bytes = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", len(html_bytes))
        self.end_headers()
        self.wfile.write(html_bytes)

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress most logging, keep errors only."""
        pass


class PreviewServer:
    """Manages the preview HTTP server lifecycle."""

    DEFAULT_PORT = 7420

    def __init__(self, port: int = DEFAULT_PORT, preview_dir: Path | None = None):
        self.port = self._find_available_port(port)
        self.preview_dir = preview_dir or _get_preview_dir()
        self.preview_dir.mkdir(parents=True, exist_ok=True)
        self.router = PreviewRouter(self.preview_dir)
        self._server: HTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._browser_opened = False

    def _find_available_port(self, start: int) -> int:
        """Find an available port starting from `start`."""
        for port in range(start, start + 100):
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.bind(("127.0.0.1", port))
                s.close()
                return port
            except OSError:
                continue
        return start  # fallback to start

    def start(self) -> str:
        """Start the preview server. Returns the URL."""
        if self._server:
            return f"http://localhost:{self.port}"

        PreviewHandler.router = self.router

        try:
            self._server = HTTPServer(("127.0.0.1", self.port), PreviewHandler)
            self._server.allow_reuse_address = True
            self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
            self._thread.start()
        except Exception as e:
            return f"Error: {e}"

        return f"http://localhost:{self.port}"

    def stop(self) -> str:
        """Stop the preview server."""
        if self._server:
            self._server.shutdown()
            self._server = None
            self._thread = None
        return "Preview server stopped"

    def preview_file(self, file_path: Path | str) -> str:
        """Preview a file, starting the server if needed. Returns the URL."""
        url = self.start()
        if not self.router.can_preview(Path(file_path)):
            return f"Cannot preview: unsupported file type {Path(file_path).suffix}"

        dest = self.router.preview_path(file_path)
        if not dest:
            return f"Error: could not copy {file_path} to preview directory"

        preview_url = f"{url}/{dest.name}"

        if not self._browser_opened:
            self._browser_opened = True
            try:
                webbrowser.open(preview_url)
            except Exception:
                pass

        return preview_url

    @property
    def is_running(self) -> bool:
        return self._server is not None

    def get_url(self) -> str:
        """Get the current server URL."""
        return f"http://localhost:{self.port}" if self._server else ""


# Global server instance
_preview_server: PreviewServer | None = None


def get_preview_server() -> PreviewServer:
    global _preview_server
    if _preview_server is None:
        _preview_server = PreviewServer()
    return _preview_server
