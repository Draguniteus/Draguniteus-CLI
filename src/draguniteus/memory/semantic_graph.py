"""Semantic Project Graph: persistent understanding of your codebase.

Tracks:
- File semantics (what each file does, not just its name)
- Decisions (why code was written a certain way)
- Relationships (dependencies, couplings)
- Patterns (recurring structures)
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

class Decision:
    def __init__(self, file_path: str, decision: str, reason: str,
                 author: str = "Draguniteus", ts: str | None = None):
        self.file_path = file_path
        self.decision = decision
        self.reason = reason
        self.author = author
        self.timestamp = ts or time.strftime("%Y-%m-%dT%H:%M:%SZ")

class SemanticNode:
    def __init__(self, path: str, node_type: str, summary: str,
                 relationships: list[str] | None = None, decisions: list | None = None):
        self.path = path
        self.type = node_type  # "file", "module", "api", "component"
        self.summary = summary
        self.relationships = relationships or []  # paths of related nodes
        self.decisions = decisions or []

class SemanticGraph:
    """Persistent semantic understanding of the project.

    Usage:
        graph = SemanticGraph(project_root)
        graph.index_file("src/auth.py", "User authentication module")
        graph.add_decision("src/auth.py", "Why we use JWT not sessions",
                          "JWT is stateless and works better with microservices")
        related = graph.find_related("src/api.py")
    """

    def __init__(self, project_root: Path | None = None):
        self.project_root = project_root or Path.cwd()
        self.graph_file = self.project_root / ".draguniteus" / "semantic_graph.json"
        self._nodes: dict[str, SemanticNode] = {}
        self._decisions: list[Decision] = []
        self._load()

    def _load(self) -> None:
        if self.graph_file.exists():
            try:
                data = json.loads(self.graph_file.read_text())
                for n in data.get("nodes", []):
                    self._nodes[n["path"]] = SemanticNode(**n)
                self._decisions = [Decision(**d) for d in data.get("decisions", [])]
            except Exception:
                pass

    def _save(self) -> None:
        self.graph_file.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "nodes": [
                {**vars(n), "decisions": [vars(d) for d in n.decisions]}
                for n in self._nodes.values()
            ],
            "decisions": [vars(d) for d in self._decisions],
        }
        self.graph_file.write_text(json.dumps(data, indent=2))

    def index_file(self, path: str, summary: str,
                   node_type: str = "file",
                   relationships: list[str] | None = None) -> None:
        node = SemanticNode(path, node_type, summary, relationships)
        self._nodes[path] = node
        self._save()

    def add_decision(self, file_path: str, decision: str, reason: str) -> None:
        dec = Decision(file_path, decision, reason)
        if file_path in self._nodes:
            self._nodes[file_path].decisions.append(dec)
        self._decisions.append(dec)
        self._save()

    def find_related(self, path: str) -> list[str]:
        node = self._nodes.get(path)
        if not node:
            return []
        return node.relationships

    def search(self, query: str) -> list[SemanticNode]:
        """Semantic search — find nodes matching a natural language query."""
        query_lower = query.lower()
        results = []
        for node in self._nodes.values():
            if (query_lower in node.summary.lower() or
                query_lower in node.path.lower() or
                any(query_lower in d.decision.lower() for d in node.decisions)):
                results.append(node)
        return results

    def explain_file(self, path: str) -> str:
        """Get a natural language explanation of a file."""
        node = self._nodes.get(path)
        if not node:
            return f"No semantic information for {path}"

        parts = [f"## {path}", f"Type: {node.type}", f"Summary: {node.summary}"]
        if node.decisions:
            parts.append("\n### Decisions")
            for d in node.decisions:
                parts.append(f"- *{d.decision}*: {d.reason}")
        if node.relationships:
            parts.append(f"\nRelated: {', '.join(node.relationships)}")
        return "\n".join(parts)


# Singleton per project
_semantic_graph_instances: dict[str, SemanticGraph] = {}


def _get_semantic_graph(project_path: Path | None = None) -> SemanticGraph:
    """Get the SemanticGraph singleton for a project."""
    proj = str((project_path or Path.cwd()).absolute())
    if proj not in _semantic_graph_instances:
        _semantic_graph_instances[proj] = SemanticGraph(project_path)
    return _semantic_graph_instances[proj]