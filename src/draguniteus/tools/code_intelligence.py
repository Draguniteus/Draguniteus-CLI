"""Code intelligence tools — LSP-like features without LSP servers.

Provides:
- Symbol index for go-to-definition
- Find references via ripgrep
- Code search and navigation
- Structural understanding via AST parsing

Uses tree-sitter for parsing when available, falls back to regex patterns.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from draguniteus.config import DEFAULT_CONFIG_DIR

# Try to import tree-sitter, optional dependency
try:
    import tree_sitter_languages
    HAS_TREESITTER = True
except ImportError:
    HAS_TREESITTER = False


# Language mapping
SUPPORTED_LANGUAGES = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".jsx": "javascript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".c": "c",
    ".cpp": "cpp",
    ".h": "c",
    ".hpp": "cpp",
}

# Symbol type filters
TYPE_KINDS = {
    "function": ["def ", "function ", "fn ", "func "],
    "class": ["class ", "struct ", "type "],
    "import": ["import ", "from ", "require"],
    "variable": ["const ", "let ", "var "],
}


def _get_language(path: str) -> str | None:
    ext = Path(path).suffix.lower()
    return SUPPORTED_LANGUAGES.get(ext)


def _get_ctags_lang_args(lang: str) -> list[str]:
    """Get ctags kind args for a language."""
    mapping = {
        "python": ["--kinds-python=f", "--kinds-python=c", "--kinds-python=i"],
        "javascript": ["--kinds-javascript=f", "--kinds-javascript=c"],
        "typescript": ["--kinds-typescript=f", "--kinds-typescript=c"],
        "go": ["--kinds-go=f", "--kinds-go=c", "--kinds-go=d"],
        "rust": ["--kinds-rust=f", "--kinds-rust=c"],
        "java": ["--kinds-java=f", "--kinds-java=c"],
    }
    return mapping.get(lang, [])


# Symbol index stored in memory and persisted
_symbol_index: dict[str, list[dict[str, Any]]] = {}
_index_loaded = False


def _load_index() -> None:
    """Load persisted symbol index from disk."""
    global _symbol_index, _index_loaded
    if _index_loaded:
        return

    index_file = DEFAULT_CONFIG_DIR / "symbol_index.json"
    if index_file.exists():
        try:
            with open(index_file, "r", encoding="utf-8") as f:
                _symbol_index = json.load(f)
        except Exception:
            _symbol_index = {}
    _index_loaded = True


def _save_index() -> None:
    """Persist symbol index to disk."""
    index_file = DEFAULT_CONFIG_DIR / "symbol_index.json"
    index_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(index_file, "w", encoding="utf-8") as f:
            json.dump(_symbol_index, f)
    except Exception:
        pass


def _build_file_index(file_path: Path, lang: str, content: str) -> list[dict[str, Any]]:
    """Extract symbols from a single file using regex patterns."""
    symbols = []

    if lang == "python":
        # Functions
        for m in re.finditer(r'^(\s*)def (\w+)', content, re.MULTILINE):
            symbols.append({
                "name": m.group(2),
                "type": "function",
                "line": content[:m.start()].count('\n') + 1,
                "file": str(file_path),
                "lang": lang,
            })
        # Classes
        for m in re.finditer(r'^class (\w+)', content, re.MULTILINE):
            symbols.append({
                "name": m.group(1),
                "type": "class",
                "line": content[:m.start()].count('\n') + 1,
                "file": str(file_path),
                "lang": lang,
            })
        # Imports
        for m in re.finditer(r'^(?:from|import)\s+(\w+)', content, re.MULTILINE):
            symbols.append({
                "name": m.group(1),
                "type": "import",
                "line": content[:m.start()].count('\n') + 1,
                "file": str(file_path),
                "lang": lang,
            })

    elif lang in ("javascript", "typescript"):
        # Function declarations
        for m in re.finditer(r'(?:function|const|let|var)\s+(\w+)\s*[=\(]', content):
            name = m.group(1)
            if name not in ('if', 'else', 'for', 'while', 'switch', 'return'):
                is_func = '(' in content[m.start():m.start()+100]
                symbols.append({
                    "name": name,
                    "type": "function" if is_func else "variable",
                    "line": content[:m.start()].count('\n') + 1,
                    "file": str(file_path),
                    "lang": lang,
                })
        # Class declarations
        for m in re.finditer(r'class\s+(\w+)', content):
            symbols.append({
                "name": m.group(1),
                "type": "class",
                "line": content[:m.start()].count('\n') + 1,
                "file": str(file_path),
                "lang": lang,
            })

    elif lang == "go":
        for m in re.finditer(r'func\s+(\w+)', content):
            symbols.append({
                "name": m.group(1),
                "type": "function",
                "line": content[:m.start()].count('\n') + 1,
                "file": str(file_path),
                "lang": lang,
            })
        for m in re.finditer(r'type\s+(\w+)\s+struct', content):
            symbols.append({
                "name": m.group(1),
                "type": "class",
                "line": content[:m.start()].count('\n') + 1,
                "file": str(file_path),
                "lang": lang,
            })

    elif lang == "rust":
        for m in re.finditer(r'fn\s+(\w+)', content):
            symbols.append({
                "name": m.group(1),
                "type": "function",
                "line": content[:m.start()].count('\n') + 1,
                "file": str(file_path),
                "lang": lang,
            })
        for m in re.finditer(r'struct\s+(\w+)', content):
            symbols.append({
                "name": m.group(1),
                "type": "class",
                "line": content[:m.start()].count('\n') + 1,
                "file": str(file_path),
                "lang": lang,
            })

    return symbols


def _collect_source_files(root_path: Path) -> list[Path]:
    """Find all source files to index."""
    patterns = ["*.py", "*.js", "*.ts", "*.jsx", "*.tsx", "*.go", "*.rs", "*.java", "*.c", "*.cpp", "*.h"]
    files = []
    for pattern in patterns:
        files.extend(root_path.rglob(pattern))
    # Exclude common non-source dirs
    exclude_dirs = {'.git', 'node_modules', '__pycache__', '.venv', 'venv', 'dist', 'build', '.tox'}
    return [f for f in files if not any(ex in f.parts for ex in exclude_dirs)]


# ---- Tool functions ----

def tool_index_code(path: str = ".", reindex: bool = False, **kwargs) -> str:
    """Index source files in a directory to build symbol database.

    Scans all source files and extracts function/class/import definitions.
    Results are cached and used by FindSymbol and GoToDefinition.
    """
    global _symbol_index, _index_loaded

    _load_index()

    root = Path(path).resolve()
    if not root.exists():
        return json.dumps({"status": "error", "error": f"Path not found: {path}"})

    files = _collect_source_files(root)
    total_symbols = 0
    indexed_files = 0

    for file_path in files:
        file_key = str(file_path)
        # Skip if cached and not reindexing
        if not reindex and file_key in _symbol_index:
            total_symbols += len(_symbol_index[file_key])
            continue

        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        lang = _get_language(str(file_path))
        if not lang:
            continue

        symbols = _build_file_index(file_path, lang, content)
        if symbols:
            _symbol_index[file_key] = symbols
            total_symbols += len(symbols)
            indexed_files += 1

    _save_index()
    _index_loaded = True

    return json.dumps({
        "status": "ok",
        "indexed_files": indexed_files,
        "total_symbols": total_symbols,
        "cached_files": len(_symbol_index),
        "path": str(root),
    })


def tool_find_symbol(symbol: str, type_filter: str = "all", **kwargs) -> str:
    """Find all definitions of a symbol in the indexed codebase.

    Uses the symbol index for fast lookup, falls back to ripgrep.

    Args:
        symbol: Symbol name to search for
        type_filter: Filter by type - function, class, import, variable, or all
    """
    import glob

    _load_index()

    results = []
    symbol_lower = symbol.lower()

    # Search indexed symbols
    for file_key, symbols in _symbol_index.items():
        for sym in symbols:
            if sym["name"].lower() == symbol_lower:
                if type_filter == "all" or sym["type"] == type_filter:
                    results.append({
                        "file": sym["file"],
                        "line": sym["line"],
                        "type": sym["type"],
                        "name": sym["name"],
                        "source": "index",
                    })

    # Fallback to ripgrep if no results
    if not results:
        try:
            proc = subprocess.run(
                ["rg", "-n", "--line-number", symbol, "."],
                capture_output=True, text=True, timeout=15
            )
            for line in proc.stdout.splitlines():
                parts = line.split(":", 2)
                if len(parts) >= 2:
                    results.append({
                        "file": parts[0],
                        "line": int(parts[1]) if parts[1].isdigit() else 0,
                        "context": parts[2][:80] if len(parts) > 2 else "",
                        "source": "grep",
                    })
        except Exception:
            pass

    if not results:
        return json.dumps({"status": "ok", "results": [], "message": f"No results for: {symbol}"})

    output = f"Found {len(results)} results for '{symbol}':\n\n"
    for r in results[:20]:  # Limit output
        source = r.get("source", "index")
        line_info = f"{r['file']}:{r['line']}"
        if source == "index":
            output += f"  [{r['type']}] {line_info}\n"
        else:
            ctx = r.get("context", "")[:60]
            output += f"  {line_info} | {ctx}\n"

    if len(results) > 20:
        output += f"\n  ... and {len(results) - 20} more"

    return json.dumps({"status": "ok", "results": results, "summary": output})


def tool_go_to_definition(symbol: str, file: str = "", **kwargs) -> str:
    """Find the definition of a symbol given its name and a file where it's used.

    Uses ctags for fast lookup, falls back to regex search in the file.
    """
    _load_index()

    if not symbol:
        return json.dumps({"status": "error", "error": "symbol name required"})

    # First try ctags for exact match
    ctags_result = _ctags_lookup(symbol, file)
    if ctags_result:
        return json.dumps({"status": "ok", "definition": ctags_result, "method": "ctags"})

    # Try searching in indexed symbols
    symbol_lower = symbol.lower()
    for file_key, symbols in _symbol_index.items():
        for sym in symbols:
            if sym["name"].lower() == symbol_lower:
                return json.dumps({
                    "status": "ok",
                    "definition": {
                        "file": sym["file"],
                        "line": sym["line"],
                        "name": sym["name"],
                        "type": sym["type"],
                    },
                    "method": "index",
                })

    # Fallback: search the file for definition patterns
    if file:
        result = _regex_definition_search(symbol, file)
        if result:
            return json.dumps({"status": "ok", "definition": result, "method": "regex"})

    return json.dumps({"status": "ok", "definition": None, "message": f"Definition not found for: {symbol}"})


def _ctags_lookup(symbol: str, file_path: str) -> dict[str, Any] | None:
    """Use ctags to look up a symbol definition."""
    try:
        # Try with ctags
        proc = subprocess.run(
            ["ctags", "-x", "--kinds-py=f", "--kinds-py=c", symbol],
            capture_output=True, text=True, timeout=5
        )
        for line in proc.stdout.splitlines():
            parts = line.split()
            if parts and parts[0] == symbol:
                return {
                    "file": parts[1] if len(parts) > 1 else file_path,
                    "line": int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 1,
                    "name": symbol,
                    "type": parts[3] if len(parts) > 3 else "symbol",
                }
    except Exception:
        pass
    return None


def _regex_definition_search(symbol: str, file_path: str) -> dict[str, Any] | None:
    """Search a file for symbol definition using regex."""
    try:
        path = Path(file_path)
        if not path.exists():
            return None

        content = path.read_text(encoding="utf-8", errors="ignore")
        lang = _get_language(file_path)

        if lang == "python":
            for pattern in [rf'^def {re.escape(symbol)}\(', rf'^class {re.escape(symbol)}']:
                m = re.search(pattern, content, re.MULTILINE)
                if m:
                    return {
                        "file": file_path,
                        "line": content[:m.start()].count('\n') + 1,
                        "name": symbol,
                        "type": "function" if pattern.startswith('^def') else "class",
                    }

        elif lang in ("javascript", "typescript"):
            for pattern in [
                rf'function\s+{re.escape(symbol)}\s*\(',
                rf'class\s+{re.escape(symbol)}\s*[{{]',
                rf'const\s+{re.escape(symbol)}\s*=\s*(?:async\s+)?\(',
            ]:
                m = re.search(pattern, content)
                if m:
                    return {
                        "file": file_path,
                        "line": content[:m.start()].count('\n') + 1,
                        "name": symbol,
                        "type": "function" if 'function' in pattern else "class",
                    }

    except Exception:
        pass

    return None


def tool_find_references(symbol: str, cwd: str = ".", **kwargs) -> str:
    """Find all references to a symbol in the codebase using ripgrep.

    Searches for all occurrences of the symbol name, useful for understanding
    where a symbol is used.
    """
    if not symbol:
        return json.dumps({"status": "error", "error": "symbol required"})

    results = []
    try:
        proc = subprocess.run(
            ["rg", "-n", "--line-number", "--color=never", symbol, cwd],
            capture_output=True, text=True, timeout=15
        )
        for line in proc.stdout.splitlines():
            parts = line.split(":", 2)
            if len(parts) >= 2:
                results.append({
                    "file": parts[0],
                    "line": int(parts[1]) if parts[1].isdigit() else 0,
                    "context": parts[2][:100] if len(parts) > 2 else "",
                })
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)})

    if not results:
        return json.dumps({"status": "ok", "references": [], "message": f"No references found for: {symbol}"})

    output = f"Found {len(results)} references to '{symbol}':\n\n"
    for r in results[:15]:
        output += f"  {r['file']}:{r['line']} | {r['context']}\n"

    if len(results) > 15:
        output += f"\n  ... and {len(results) - 15} more"

    return json.dumps({"status": "ok", "references": results, "summary": output})


# Tool definitions for ALL_TOOLS
CODE_INDEX_TOOLS = [
    {
        "name": "IndexCode",
        "description": """Index the codebase to build a symbol database for code intelligence.

Scans all source files and extracts function/class/import definitions.
Results are cached and used by FindSymbol and GoToDefinition.

Use this when starting work on a new project or after adding new files.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to directory to index (defaults to current directory)",
                },
                "reindex": {
                    "type": "boolean",
                    "description": "Force re-indexing even if index exists",
                },
            },
        },
    },
    {
        "name": "FindSymbol",
        "description": """Find all definitions of a symbol in the codebase.

Uses cached symbol index for fast lookup, falls back to ripgrep.
Returns file paths and line numbers for each match.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Symbol name to search for",
                },
                "type": {
                    "type": "string",
                    "description": "Filter by symbol type: function, class, import, variable, or all",
                    "enum": ["function", "class", "import", "variable", "all"],
                },
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "GoToDefinition",
        "description": """Find the definition/declaration of a symbol.

Given a symbol name and file where it's used, finds the actual definition.
Uses ctags for fast lookup, falls back to regex search.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Symbol name to find definition for",
                },
                "file": {
                    "type": "string",
                    "description": "File path where the symbol is used",
                },
            },
            "required": ["symbol", "file"],
        },
    },
    {
        "name": "FindReferences",
        "description": """Find all references to a symbol in the codebase.

Uses ripgrep to find all occurrences of the symbol name.
Returns file:line:context for each match.

Use this to understand where a symbol is used before refactoring.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Symbol name to find references for",
                },
                "cwd": {
                    "type": "string",
                    "description": "Directory to search in (defaults to current directory)",
                },
            },
            "required": ["symbol"],
        },
    },
]