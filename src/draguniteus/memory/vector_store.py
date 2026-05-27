"""ChromaDB-backed vector memory for semantic search.

Collection per project at .draguniteus/chroma_db/ with fallback to
difflib-based approximate search if ChromaDB is unavailable.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
from pathlib import Path
from typing import Any

# Try ChromaDB, fall back gracefully
try:
    import chromadb
    from chromadb.config import Settings as ChromaSettings
    CHROMA_AVAILABLE = True
except Exception:
    CHROMA_AVAILABLE = False

from draguniteus.config import DEFAULT_CONFIG_DIR


def _get_config_dir() -> Path:
    if platform.system() == "Windows":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path.home()
    return base / ".draguniteus"


class VectorMemory:
    """ChromaDB-backed semantic memory with in-memory fallback.

    Each project gets a collection at .draguniteus/chroma_db/<project_hash>/
    Falls back to difflib-based search if ChromaDB is not installed.
    """

    def __init__(self, project_path: Path | None = None):
        self.project_path = project_path or Path.cwd()
        self.project_hash = hashlib.md5(str(self.project_path.absolute()).encode()).hexdigest()[:12]
        self.chroma_dir = _get_config_dir() / "chroma_db" / self.project_hash
        self._client = None
        self._collection = None
        self._use_fallback = not CHROMA_AVAILABLE

        if CHROMA_AVAILABLE:
            try:
                self.chroma_dir.mkdir(parents=True, exist_ok=True)
                self._client = chromadb.PersistentClient(
                    path=str(self.chroma_dir),
                    settings=ChromaSettings(anonymized_telemetry=False),
                )
                self._collection = self._client.get_or_create_collection(
                    name="draguniteus_memory",
                    metadata={"project": str(self.project_path)},
                )
            except Exception:
                self._use_fallback = True
                self._client = None
                self._collection = None

        # Fallback: in-memory store
        self._fallback_docs: list[dict] = []

    def add(
        self,
        content: str,
        doc_type: str = "general",
        path: str = "",
        tags: list[str | None] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Add a document to vector memory. Returns the document ID."""
        doc_id = hashlib.sha256(content.encode()).hexdigest()[:16]

        if self._collection is not None:
            try:
                self._collection.add(
                    documents=[content],
                    metadatas=[{
                        "type": doc_type,
                        "path": path,
                        "tags": json.dumps(tags or []),
                        **(metadata or {}),
                    }],
                    ids=[doc_id],
                )
            except Exception:
                # Fall through to in-memory
                self._fallback_docs.append({
                    "id": doc_id,
                    "content": content,
                    "type": doc_type,
                    "path": path,
                    "tags": tags or [],
                })
        else:
            self._fallback_docs.append({
                "id": doc_id,
                "content": content,
                "type": doc_type,
                "path": path,
                "tags": tags or [],
            })

        return doc_id

    def search(
        self,
        query: str,
        n_results: int = 5,
        doc_type: str | None = None,
        tags: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Search for semantically similar documents."""
        if self._collection is not None:
            try:
                where_filter: dict[str, Any] = {}
                if doc_type:
                    where_filter["type"] = doc_type

                results = self._collection.query(
                    query_texts=[query],
                    n_results=n_results,
                    where=where_filter if where_filter else None,
                )

                docs = []
                if results and results.get("documents"):
                    for i, doc in enumerate(results["documents"][0]):
                        meta = results["metadatas"][0][i] if results.get("metadatas") else {}
                        docs.append({
                            "id": results["ids"][0][i],
                            "content": doc,
                            "type": meta.get("type", "general"),
                            "path": meta.get("path", ""),
                            "tags": json.loads(meta.get("tags", "[]")),
                            "distance": results.get("distances", [[]])[0][i] if results.get("distances") else 0.0,
                        })
                return docs
            except Exception:
                pass

        # Fallback: simple content match via difflib
        return self._fallback_search(query, n_results, doc_type, tags)

    def _fallback_search(
        self,
        query: str,
        n_results: int = 5,
        doc_type: str | None = None,
        tags: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Simple fallback search using difflib similarity."""
        import difflib

        scored = []
        query_lower = query.lower()
        for doc in self._fallback_docs:
            if doc_type and doc.get("type") != doc_type:
                continue
            if tags:
                doc_tags = doc.get("tags", [])
                if not any(t in doc_tags for t in tags if t):
                    continue
            ratio = difflib.SequenceMatcher(None, query_lower, doc["content"].lower()).ratio()
            scored.append((ratio, doc))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [{"id": d["id"], "content": d["content"], "type": d.get("type", "general"),
                 "path": d.get("path", ""), "tags": d.get("tags", []), "distance": 1.0 - s}
                for s, d in scored[:n_results]]

    def delete(self, doc_id: str) -> bool:
        """Delete a document by ID."""
        if self._collection is not None:
            try:
                self._collection.delete(ids=[doc_id])
                return True
            except Exception:
                pass

        for i, doc in enumerate(self._fallback_docs):
            if doc["id"] == doc_id:
                self._fallback_docs.pop(i)
                return True
        return False

    def count(self) -> int:
        """Return total document count."""
        if self._collection is not None:
            try:
                return self._collection.count()
            except Exception:
                pass
        return len(self._fallback_docs)

    def clear(self) -> None:
        """Clear all documents for this project."""
        if self._collection is not None:
            try:
                self._client.delete_collection(name="draguniteus_memory")
                self._collection = self._client.get_or_create_collection(
                    name="draguniteus_memory",
                    metadata={"project": str(self.project_path)},
                )
            except Exception:
                pass
        self._fallback_docs.clear()


# Global per-project instances (lazy)
_vector_memory_instances: dict[str, VectorMemory] = {}


def get_vector_memory(project_path: Path | None = None) -> VectorMemory:
    """Get the VectorMemory instance for a project (singleton per project)."""
    proj = (project_path or Path.cwd()).absolute()
    key = str(proj)
    if key not in _vector_memory_instances:
        _vector_memory_instances[key] = VectorMemory(proj)
    return _vector_memory_instances[key]
