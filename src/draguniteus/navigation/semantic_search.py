"""Semantic Code Navigation: find code by meaning, not just name.

Usage:
    nav = SemanticNavigator(project_root)
    results = nav.search("authentication middleware")
    # Returns files/functions that handle auth middleware semantically
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

class SemanticNavigator:
    """Navigate codebase by semantic meaning.

    Understands what code DOES, not just what it's named.
    Uses the semantic graph + code analysis.
    """

    def __init__(self, project_root: Path | None = None):
        self.project_root = project_root or Path.cwd()
        self.graph = None  # Lazy load
        self._index_prewarmed = False
        self._prewarm_done = False

    def _get_graph(self):
        if self.graph is None:
            from draguniteus.memory.semantic_graph import SemanticGraph
            self.graph = SemanticGraph(self.project_root)
        return self.graph

    def prewarm_index(self, background: bool = True) -> None:
        """Pre-build the semantic index in background for faster first search.

        Call this after CLI starts for snappy semantic search on first query.
        """
        import threading
        if background and not self._prewarm_done:
            self._prewarm_done = True
            t = threading.Thread(target=self._do_prewarm, daemon=True)
            t.start()
        elif not background:
            self._do_prewarm()

    def _do_prewarm(self) -> None:
        """Walk project and index files with meaningful names."""
        from draguniteus.memory.semantic_graph import SemanticGraph
        graph = SemanticGraph(self.project_root)
        try:
            for f in self.project_root.rglob("*.py"):
                path_str = str(f)
                if any(skip in path_str for skip in [".venv", "node_modules", "__pycache__", ".git"]):
                    continue
                # Don't overwrite existing entries
                if path_str not in graph._nodes:
                    graph.index_file(
                        path=path_str,
                        summary=f"Python module at {f.stem}",
                        node_type="file",
                        relationships=[],
                    )
        except Exception:
            pass

    def search(self, query: str, max_results: int = 10) -> list[dict[str, Any]]:
        """Find code matching a natural language description.

        Returns list of {path, line_number, snippet, relevance, search_mode} dicts.
        search_mode is "semantic" if matched via graph, "content" if via grep fallback.
        """
        results = []
        semantic_mode = True

        # First try semantic graph
        graph = self._get_graph()
        semantic_matches = graph.search(query)
        for node in semantic_matches[:max_results]:
            results.append({
                "path": node.path,
                "line_number": 1,
                "snippet": node.summary,
                "relevance": "high",
                "type": "semantic",
                "search_mode": "semantic",
            })

        # Then search file contents with semantic understanding
        code_matches = self._semantic_content_search(query, max_results)
        if code_matches:
            semantic_mode = False  # At least one content match found
        results.extend(code_matches)

        # Deduplicate by path
        seen = set()
        unique = []
        for r in results:
            if r["path"] not in seen:
                seen.add(r["path"])
                unique.append(r)
        results = unique[:max_results]

        # Mark results that came from grep fallback
        if semantic_mode and not semantic_matches and not code_matches:
            semantic_mode = False  # No graph entries at all

        return results

    def search_with_mode(self, query: str, max_results: int = 10) -> tuple[list[dict], str]:
        """search() but also returns which mode was used: 'semantic', 'content', or 'mixed'."""
        results = self.search(query, max_results)
        modes = {r.get("search_mode", "content") for r in results}
        if "content" in modes and "semantic" in modes:
            mode = "mixed"
        elif "content" in modes:
            mode = "content"
        elif "semantic" in modes:
            mode = "semantic"
        else:
            mode = "empty"

        # Also flag if the graph was completely empty (first search)
        if not self._get_graph()._nodes:
            mode = "first_search (graph empty, used grep)"
        elif mode == "content" and not results:
            mode = "empty (no graph entries, used grep)"

        return results, mode

    def _semantic_content_search(self, query: str, max_results: int) -> list[dict]:
        """Search file contents with semantic understanding."""
        results = []
        # Use code intelligence tools if available
        try:
            from draguniteus.tools.code_intelligence import tool_grep
            # Search for files containing relevant keywords
            keywords = self._extract_keywords(query)
            for kw in keywords[:5]:
                matches = tool_grep(query=kw, path=str(self.project_root),
                                   max_results=3)
                if matches:
                    for m in matches:
                        results.append({
                            "path": m.get("path", ""),
                            "line_number": m.get("line_number", 1),
                            "snippet": m.get("content", "")[:200],
                            "relevance": "medium",
                            "type": "content",
                        })
        except Exception:
            pass
        return results

    def _extract_keywords(self, query: str) -> list[str]:
        """Extract keywords from natural language query."""
        stop_words = {"the", "a", "an", "is", "are", "was", "where", "what",
                      "how", "why", "file", "function", "code", "that", "this",
                      "it", "in", "of", "to", "for", "with"}
        words = re.findall(r'\w+', query.lower())
        return [w for w in words if w not in stop_words and len(w) > 2]

    def find_by_example(self, description: str) -> str | None:
        """Find code matching an example description.

        e.g. "find the function that handles Stripe webhook validation"
        """
        results = self.search(description, max_results=3)
        if results:
            best = results[0]
            return f"{best['path']}:{best['line_number']}\n{best['snippet']}"
        return None