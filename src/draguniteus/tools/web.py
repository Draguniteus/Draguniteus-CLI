"""Web tools: WebFetch and WebSearch."""
from __future__ import annotations

import os
from typing import Any

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


WEB_TOOLS: list[dict[str, Any]] = [
    {
        "name": "WebFetch",
        "description": "Fetch content from a URL and extract information from it. " +
                       "Use for retrieving documentation, reading web pages, or accessing API responses.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL to fetch content from."
                },
                "prompt": {
                    "type": "string",
                    "description": "What information to extract from the page."
                }
            },
            "required": ["url"]
        }
    },
    {
        "name": "WebSearch",
        "description": "Search the web for current information on any topic. " +
                       "Use when you need up-to-date facts, prices, news, or documentation.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query to look up."
                }
            },
            "required": ["query"]
        }
    },
]


def tool_webfetch(url: str, prompt: str | None = None) -> str:
    """Fetch content from a URL."""
    if not HAS_REQUESTS:
        return "WebFetch requires the 'requests' library. Install with: pip install requests"

    try:
        resp = requests.get(url, timeout=30, headers={
            "User-Agent": "Mozilla/5.0 Draguniteus/0.1.0"
        })
        resp.raise_for_status()

        content = resp.text

        if prompt:
            # Simple extraction - return content with context
            return f"[Fetched {url}]\n\n{content[:5000]}"

        return f"[Fetched {url} - {len(content)} chars]\n\n{content[:8000]}"

    except Exception as e:
        return f"WebFetch error: {e}"


def tool_websearch(query: str) -> str:
    """Search the web using Tavily API (preferred) or DuckDuckGo HTML (fallback)."""
    if not HAS_REQUESTS:
        return "WebSearch requires the 'requests' library. Install with: pip install requests"

    # Try Tavily first (better results, proper API)
    tavily_key = os.environ.get("TAVILY_API_KEY")
    if tavily_key:
        try:
            import urllib.parse
            import json as json_module
            encoded_query = urllib.parse.quote(query)
            url = f"https://api.tavily.com/search?api_key={tavily_key}&query={encoded_query}&max_results=10"
            resp = requests.get(url, timeout=30, headers={
                "User-Agent": "Draguniteus/0.1.0"
            })
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("results", [])
                if results:
                    lines = ["[Web Search Results (Tavily)]"]
                    for r in results[:10]:
                        title = r.get("title", "No title")
                        url = r.get("url", "")
                        snippet = r.get("content", "")[:200]
                        lines.append(f"- {title}\n  {url}\n  {snippet}")
                    return "\n".join(lines)
        except Exception:
            pass  # Fall back to DuckDuckGo

    # Fallback to DuckDuckGo Lite (simpler, less blocking)
    try:
        import urllib.parse

        # Try DuckDuckGo Lite first (simpler HTML, less likely to block)
        for search_url in [
            f"https://lite.duckduckgo.com/lite/?q={urllib.parse.quote(query)}",
            f"https://duckduckgo.com/html/?q={urllib.parse.quote(query)}",
        ]:
            try:
                resp = requests.get(search_url, timeout=30, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                })
                resp.raise_for_status()

                # Parse results from HTML
                results = []
                import re

                # For DuckDuckGo Lite
                pattern = r'<a class="result__a" href="([^"]+)"[^>]*>([^<]+)</a>'
                matches = re.findall(pattern, resp.text)

                for url, title in matches[:10]:
                    results.append(f"- {title}\n  {url}")

                if results:
                    return "[Web Search Results]\n\n" + "\n".join(results)

                # If no results, try alternative pattern for Lite
                if not results:
                    pattern = r'<a href="(https?://[^"]+)"[^>]*>\s*([^<]+)\s*</a>'
                    matches = re.findall(pattern, resp.text)
                    for url, title in matches[:10]:
                        if title.strip() and url.startswith('http'):
                            results.append(f"- {title.strip()}\n  {url}")

                if results:
                    return "[Web Search Results]\n\n" + "\n".join(results)

            except Exception:
                continue

        # If we got here, both DuckDuckGo attempts failed - use fallback
        return tool_websearch_fallback(query)

    except Exception as e:
        return f"WebSearch error: {e}"


def tool_websearch_fallback(query: str) -> str:
    """Fallback search using free SerpAPI-like endpoint or message.

    This is called when both Tavily and DuckDuckGo fail.
    """
    # Check for SerpAPI key
    serp_key = os.environ.get("SERP_API_KEY")
    if serp_key:
        try:
            import urllib.parse
            import json as json_module
            url = f"https://serpapi.com/search.json?q={urllib.parse.quote(query)}&api_key={serp_key}"
            resp = requests.get(url, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("organic_results", [])
                if results:
                    lines = ["[Web Search Results (SerpAPI)]"]
                    for r in results[:10]:
                        title = r.get("title", "No title")
                        link = r.get("link", "")
                        snippet = r.get("snippet", "")[:200]
                        lines.append(f"- {title}\n  {link}\n  {snippet}")
                    return "\n".join(lines)
        except Exception:
            pass

    # Check for Brave Search API key
    brave_key = os.environ.get("BRAVE_SEARCH_API_KEY")
    if brave_key:
        try:
            import urllib.parse
            import json as json_module
            encoded_query = urllib.parse.quote(query)
            url = f"https://api.search.brave.com/res/v1/search?q={encoded_query}&count=10"
            resp = requests.get(url, timeout=30, headers={
                "Accept": "application/json",
                "X-Subscription-Token": brave_key
            })
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("web", {}).get("results", [])
                if results:
                    lines = ["[Web Search Results (Brave)]"]
                    for r in results[:10]:
                        title = r.get("title", "No title")
                        url = r.get("url", "")
                        snippet = r.get("description", "")[:200]
                        lines.append(f"- {title}\n  {url}\n  {snippet}")
                    return "\n".join(lines)
        except Exception:
            pass

    return "[WebSearch unavailable] Both Tavily and DuckDuckGo are blocked. Set TAVILY_API_KEY or SERP_API_KEY environment variable for web search."
