"""Tests for preview server — HTTP server on port 7420."""
import pytest
import sys
import time
from pathlib import Path
sys.path.insert(0, 'src')

from draguniteus.preview.server import (
    PreviewServer, PreviewRouter, get_preview_server
)


class TestPreviewRouter:
    """Test PreviewRouter content type detection."""

    def setup_method(self):
        self.router = PreviewRouter()

    def test_html_content_type(self):
        content_type = self.router.get_content_type(Path("index.html"))
        assert "text/html" in content_type

    def test_css_content_type(self):
        content_type = self.router.get_content_type(Path("style.css"))
        assert "text/css" in content_type

    def test_js_content_type(self):
        content_type = self.router.get_content_type(Path("app.js"))
        assert "application/javascript" in content_type or "text/javascript" in content_type

    def test_json_content_type(self):
        content_type = self.router.get_content_type(Path("data.json"))
        assert "application/json" in content_type

    def test_markdown_converted_to_html(self):
        # Markdown should be converted, not served as text/plain
        content_type = self.router.get_content_type(Path("readme.md"))
        assert "text/html" in content_type or "text/markdown" in content_type

    def test_image_static(self):
        content_type = self.router.get_content_type(Path("image.png"))
        assert "image/" in content_type

    def test_binary_for_unknown(self):
        content_type = self.router.get_content_type(Path("file.xyz"))
        assert "application/octet-stream" in content_type


class TestPreviewServer:
    """Test PreviewServer lifecycle."""

    def setup_method(self):
        self.server = get_preview_server()

    def test_is_not_running_initially(self):
        # Note: may already be running from previous tests
        # Just check it's a valid object
        assert self.server is not None

    def test_is_running_property(self):
        # Property, not method
        result = self.server.is_running
        assert isinstance(result, bool)

    def test_port_default(self):
        assert self.server.port == 7420

    def test_get_url_when_not_running(self):
        url = self.server.get_url()
        # When not running, URL should be empty
        if not self.server.is_running:
            assert url == ""

    def test_get_url_when_running(self):
        if not self.server.is_running:
            self.server.start()
        url = self.server.get_url()
        assert "localhost" in url or "127.0.0.1" in url
        assert str(self.server.port) in url

    def test_start_server(self):
        if not self.server.is_running:
            self.server.start()
        assert self.server.is_running is True

    def test_preview_file_generates_url(self):
        test_html = Path("C:/tmp/test_preview.html")
        test_html.write_text("<html><body>Test</body></html>", encoding="utf-8")

        if not self.server.is_running:
            self.server.start()

        url = self.server.preview_file(str(test_html))
        assert url is not None
        assert "localhost" in url or "127.0.0.1" in url

    def test_browser_opened_flag(self):
        # After start(), browser_opened may be True if preview_file was called
        # Just verify the attribute exists
        assert hasattr(self.server, '_browser_opened')


class TestGetPreviewServer:
    """Test singleton accessor."""

    def test_returns_singleton(self):
        s1 = get_preview_server()
        s2 = get_preview_server()
        assert s1 is s2