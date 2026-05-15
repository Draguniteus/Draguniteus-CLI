"""Pattern Library: learned code patterns that improve over time.

Learns from successful implementations across ALL projects Draguniteus works on.
Stores reusable patterns, when to apply them, and success metrics.

Uses a singleton instance to avoid reloading all patterns from disk on every
PatternLibrary() instantiation.
"""
from __future__ import annotations

import json
import time
import threading
from pathlib import Path
from typing import Any

class Pattern:
    def __init__(self, name: str, description: str, code: str,
                 language: str, tags: list[str],
                 when_to_use: str, success_count: int = 0,
                 fail_count: int = 0, examples: list[str] | None = None):
        self.id = f"p_{int(time.time() * 1000)}"
        self.name = name
        self.description = description
        self.code = code
        self.language = language
        self.tags = tags
        self.when_to_use = when_to_use
        self.success_count = success_count
        self.fail_count = fail_count
        self.examples = examples or []
        self.created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ")
        self.last_used = self.created_at

# Singleton instance — shared across all callers
_instance: "PatternLibrary | None" = None
_instance_lock = threading.Lock()


def _get_pattern_library() -> "PatternLibrary":
    """Get or create the singleton PatternLibrary instance."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = PatternLibrary()
    return _instance


class PatternLibrary:
    """Learns and stores code patterns across all projects.

    Usage:
        lib = PatternLibrary()
        lib.learn(successful_code, "authentication", language="python")
        patterns = lib.search("JWT token handling")
        suggested = lib.suggest_for_context("adding OAuth to Flask app")
    """

    def __init__(self):
        self.patterns_dir = Path.home() / ".draguniteus" / "patterns"
        self.patterns_dir.mkdir(parents=True, exist_ok=True)
        self._patterns: list[Pattern] = []
        self._load_all()

    def _load_all(self) -> None:
        for f in self.patterns_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text())
                self._patterns.append(Pattern(**data))
            except Exception:
                pass

    def _save(self, pattern: Pattern) -> None:
        f = self.patterns_dir / f"{pattern.id}.json"
        f.write_text(json.dumps(vars(pattern), indent=2))

    def learn(self, code: str, category: str, language: str,
              when_to_use: str = "", example_use: str = "") -> Pattern:
        """Learn a new pattern from successful code.

        Call this after a successful implementation to store the pattern.
        """
        import hashlib
        name = f"{category}_{hashlib.md5(code[:100].encode()).hexdigest()[:8]}"
        tags = [category, language]

        pattern = Pattern(
            name=name,
            description=f"{category} pattern in {language}",
            code=code[:2000],  # Store first 2000 chars
            language=language,
            tags=tags,
            when_to_use=when_to_use,
            examples=[example_use] if example_use else [],
        )
        self._patterns.append(pattern)
        self._save(pattern)
        return pattern

    def search(self, query: str, max_results: int = 5) -> list[Pattern]:
        """Find patterns matching a natural language query."""
        query_lower = query.lower()
        scored = []
        for p in self._patterns:
            score = 0
            if query_lower in p.description.lower():
                score += 3
            if query_lower in p.when_to_use.lower():
                score += 2
            if any(query_lower in t.lower() for t in p.tags):
                score += 2
            if query_lower in p.code.lower():
                score += 1
            if score > 0:
                scored.append((score, p))

        scored.sort(reverse=True)
        return [p for _, p in scored[:max_results]]

    def suggest_for_context(self, context: str, code_snippet: str = "") -> list[Pattern]:
        """Suggest patterns relevant to the current task context.

        Uses both the natural language context AND the current code snippet
        to find the most relevant patterns.

        e.g. suggest_for_context("adding rate limiting to API endpoint",
                                 code_snippet="def api_handler(request): ...")
        """
        import re
        # Extract key topics from context
        stop = {"the", "a", "an", "to", "for", "in", "of", "and", "or", "with", "adding",
                "using", "how", "what", "this", "that", "file", "function", "code"}
        words = re.findall(r'\w+', context.lower())
        topics = [w for w in words if w not in stop and len(w) > 2]

        # Extract topics from code snippet too
        if code_snippet:
            code_words = re.findall(r'\w+', code_snippet.lower())
            code_topics = [w for w in code_words if w not in stop and len(w) > 3]
            topics.extend(code_topics[:5])

        suggestions = []
        for p in self._patterns:
            score = 0
            # Tag match
            tag_match = sum(1 for t in topics if t in [tag.lower() for tag in p.tags])
            score += tag_match * 3

            # Context keyword match in description
            for t in topics:
                if t in p.description.lower():
                    score += 2
                if t in p.when_to_use.lower():
                    score += 2
                if t in p.code.lower():
                    score += 1

            # Prefer patterns with higher success rate
            total = p.success_count + p.fail_count + 1
            success_rate = p.success_count / total
            score += success_rate * 2  # Up to +2 for 100% success rate

            if score > 0:
                suggestions.append((score, p))

        suggestions.sort(key=lambda x: -x[0])
        return [p for _, p in suggestions[:5]]

    def record_outcome(self, pattern_id: str, success: bool) -> None:
        """Record whether a pattern worked well in practice."""
        for p in self._patterns:
            if p.id == pattern_id:
                if success:
                    p.success_count += 1
                else:
                    p.fail_count += 1
                p.last_used = time.strftime("%Y-%m-%dT%H:%M:%SZ")
                self._save(p)
                break

    def learn_from_tool_sequence(self, tool_names: list[str], code: str,
                                  language: str, task: str) -> Pattern | None:
        """Learn a pattern from a successful tool-use sequence.

        Call this when a sequence of tools successfully completed a task.
        The code should be the final output code from the sequence.

        Returns the learned pattern or None if nothing worth learning.
        """
        if not code or len(code) < 50:
            return None

        # Create a category from the tool sequence
        category = "_".join(tool_names[:3])
        when_to_use = f"Tool sequence: {' -> '.join(tool_names)}. Task: {task[:100]}"

        return self.learn(
            code=code,
            category=category,
            language=language,
            when_to_use=when_to_use,
            example_use=task[:200],
        )

    def get_stats(self) -> dict[str, Any]:
        """Get pattern library statistics."""
        if not self._patterns:
            return {"total": 0, "by_language": {}, "top_tags": []}

        total = len(self._patterns)
        by_lang: dict[str, int] = {}
        tag_counts: dict[str, int] = {}
        total_success = 0
        total_fail = 0

        for p in self._patterns:
            by_lang[p.language] = by_lang.get(p.language, 0) + 1
            for tag in p.tags:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
            total_success += p.success_count
            total_fail += p.fail_count

        top_tags = sorted(tag_counts.items(), key=lambda x: -x[1])[:10]

        return {
            "total": total,
            "by_language": by_lang,
            "top_tags": top_tags,
            "total_successes": total_success,
            "total_failures": total_fail,
        }