"""Navigation tools: semantic code search."""
from __future__ import annotations

from typing import Any


NAVIGATION_TOOLS = [
    {
        "name": "SemanticSearch",
        "description": "Find code using natural language descriptions, not just filenames. 'Find the function that handles Stripe webhook validation' — understands semantics.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language description of what you're looking for"
                },
                "max_results": {
                    "type": "integer",
                    "default": 10,
                    "description": "Maximum number of results to return"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "ExplainCode",
        "description": "Get a semantic explanation of a file — what it does, why it was written that way, and how it relates to other code. Uses the semantic project graph.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file to explain"
                }
            },
            "required": ["path"]
        }
    },
    {
        "name": "IndexSemantic",
        "description": "Teach Draguniteus what a file or component does semantically. After this, SemanticSearch can find it by meaning. Use after implementing a new module.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file or directory"
                },
                "summary": {
                    "type": "string",
                    "description": "What this code does in one sentence"
                },
                "component_type": {
                    "type": "string",
                    "enum": ["file", "module", "api", "component", "test"],
                    "description": "Type of component"
                },
                "related_paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Paths of related files/modules"
                }
            },
            "required": ["path", "summary"]
        }
    }
]


def tool_semantic_search(query: str, max_results: int = 10, **kwargs) -> str:
    """Find code by natural language meaning."""
    try:
        from draguniteus.navigation.semantic_search import SemanticNavigator

        nav = SemanticNavigator()
        results, mode = nav.search_with_mode(query, max_results=max_results)

        if not results:
            mode_note = f" ({mode})" if mode else ""
            return f"No results found for: `{query}`{mode_note}"

        mode_note = f" [mode: {mode}]" if mode else ""
        lines = [f"## Semantic Search: {query}{mode_note}\n"]
        for r in results:
            search_type = r.get("search_mode", "content")
            badge = "🏷️" if search_type == "semantic" else "🔍"
            lines.append(f"**{r['path']}** (line {r.get('line_number', '?')}) {badge}")
            lines.append(f"  {r.get('snippet', '')[:200]}")
            lines.append(f"  _relevance: {r.get('relevance', 'unknown')} — {search_type}_")
            lines.append("")

        return "\n".join(lines)
    except Exception as e:
        return f"Semantic search error: {e}"


def tool_explain_code(path: str, **kwargs) -> str:
    """Get semantic explanation of a file."""
    try:
        from draguniteus.memory.semantic_graph import SemanticGraph

        graph = SemanticGraph()
        explanation = graph.explain_file(path)
        if "No semantic information" not in explanation:
            return explanation

        # Fallback: use code intelligence for symbol analysis
        from draguniteus.tools.code_intelligence import tool_find_symbol
        from pathlib import Path

        p = Path(path)
        if not p.exists():
            return f"File not found: {path}"

        content = p.read_text(errors="ignore")
        lines = content.split("\n")
        symbol_lines = []
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("def ") or stripped.startswith("class "):
                symbol_lines.append(f"  line {i}: {stripped}")

        result = [
            f"## {path}",
            f"No semantic graph entry (run `/index {path} <summary>` to add).",
            "",
            f"### Symbols found ({len(symbol_lines)}):\n" if symbol_lines else "### No function/class definitions found.\n",
        ]
        result.extend(symbol_lines[:20])

        return "\n".join(result)
    except Exception as e:
        return f"Explain error: {e}"


def tool_index_semantic(
    path: str,
    summary: str,
    component_type: str = "file",
    related_paths: list[str] | None = None,
    **kwargs
) -> str:
    """Index a file semantically in the project graph."""
    try:
        from draguniteus.memory.semantic_graph import SemanticGraph

        graph = SemanticGraph()
        graph.index_file(
            path=path,
            summary=summary,
            node_type=component_type,
            relationships=related_paths or []
        )
        return f"Indexed: {path} as {component_type} — {summary}"
    except Exception as e:
        return f"Index error: {e}"
