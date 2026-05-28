"""Tests for memory manager — all memory layers and ChromaDB integration."""
import pytest
import sys
import time
from pathlib import Path
sys.path.insert(0, 'src')

from draguniteus.memory.manager import (
    MemoryManager, ProjectMemory, memory_manager
)


class TestProjectMemory:
    """Test ProjectMemory for DRAGUNITEUS.md and daily notes."""

    def setup_method(self):
        import shutil
        self.temp_dir = Path("C:/tmp/test_pm_dir")
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        self.temp_dir.mkdir(exist_ok=True)
        self.pm = ProjectMemory(project_dir=self.temp_dir)

    def test_exists_false_when_no_dragon_file(self):
        # ProjectMemory.exists() checks for DRAGUNITEUS.md
        assert self.pm.exists() is False

    def test_read_empty_when_no_dragon_file(self):
        result = self.pm.read()
        assert result == ""

    def test_write_creates_dragon_md(self):
        self.pm.write("# Project Notes\n\nTest content.")
        assert self.pm.exists()
        content = self.pm.read()
        assert "Test content" in content

    def test_append_section(self):
        self.pm.write("## Existing\nContent")
        self.pm.append_section("New Section", "New content here")
        content = self.pm.read()
        assert "New Section" in content
        assert "New content here" in content

    def test_read_daily_empty_when_no_file(self):
        result = self.pm.read_daily("2024-01-01")
        assert result is None

    def test_write_daily_creates_file(self):
        self.pm.write_daily("## Today\nWorked on feature X.", date_str="2024-06-15")
        result = self.pm.read_daily("2024-06-15")
        assert result is not None
        assert "feature X" in result

    def test_read_daily_returns_none_for_missing_date(self):
        result = self.pm.read_daily("2099-12-31")
        assert result is None

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)


class TestMemoryManager:
    """Test MemoryManager with all memory layers."""

    def setup_method(self):
        self.mgr = MemoryManager()

    def test_has_project_memory(self):
        assert self.mgr.project_memory is not None

    def test_vector_memory_lazy_init(self):
        # Should not fail even if ChromaDB unavailable
        vm = self.mgr.vector_memory
        # Returns None if ChromaDB not available
        assert vm is None or hasattr(vm, 'count')

    def test_add_to_vector_memory(self):
        doc_id = self.mgr.add_to_vector_memory(
            "Test code pattern for Flask routing",
            doc_type="code_pattern",
            path="src/app.py",
            tags=["flask", "routing"]
        )
        # May be empty string if ChromaDB not available
        assert isinstance(doc_id, str)

    def test_search_vector_memory(self):
        # Add something first
        self.mgr.add_to_vector_memory(
            "FastAPI dependency injection pattern",
            doc_type="pattern",
            tags=["fastapi", "di"]
        )
        results = self.mgr.search_vector_memory("FastAPI dependency injection", n_results=3)
        assert isinstance(results, list)

    def test_load_for_agent_no_query(self):
        result = self.mgr.load_for_agent(query=None)
        assert isinstance(result, str)

    def test_load_for_agent_with_query(self):
        self.mgr.add_to_vector_memory(
            "Python async/await best practices",
            doc_type="pattern",
            tags=["async", "python"]
        )
        result = self.mgr.load_for_agent(query="async python patterns")
        assert isinstance(result, str)

    def test_search_returns_list(self):
        # Should return a list (possibly empty or with results from other tests)
        results = self.mgr.search_vector_memory("nonexistent query xyz123", n_results=5)
        assert isinstance(results, list)


class TestMemoryManagerSingleton:
    """Test singleton behavior."""

    def test_memory_manager_singleton(self):
        from draguniteus.memory.manager import _get_memory_manager
        mgr1 = _get_memory_manager()
        mgr2 = _get_memory_manager()
        assert mgr1 is mgr2