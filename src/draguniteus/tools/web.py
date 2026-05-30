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
    """Search the web using Tavily API (primary) or MiniMax built-in search.

    MiniMax token plans include web search - we should use Tavily API with the
    user's provided key, not DuckDuckGo as fallback.
    """
    if not HAS_REQUESTS:
        return "WebSearch requires the 'requests' library. Install with: pip install requests"

    # Primary: Use Tavily API with user's provided key
    # Check env var first, then use the user's direct Tavily key
    tavily_key = os.environ.get("TAVILY_API_KEY") or "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"

    if tavily_key:
        try:
            import urllib.parse
            import json as json_module
            # Tavily API uses POST with JSON body, not GET with query params
            payload = json_module.dumps({"api_key": tavily_key, "query": query, "max_results": 10})
            resp = requests.post(
                "https://api.tavily.com/search",
                data=payload,
                timeout=30,
                headers={
                    "User-Agent": "Draguniteus/0.1.0",
                    "Content-Type": "application/json"
                }
            )
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
            elif resp.status_code == 401:
                return "[WebSearch error] Invalid Tavily API key. Please check your key or set TAVILY_API_KEY environment variable."
        except Exception as e:
            pass  # Will fall through to other options

    # Fallback: SerpAPI if available
    serp_key = os.environ.get("SERP_API_KEY")
    if serp_key:
        try:
            import urllib.parse
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

    # Final fallback: Brave Search API
    brave_key = os.environ.get("BRAVE_SEARCH_API_KEY")
    if brave_key:
        try:
            import urllib.parse
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

    return "[WebSearch unavailable] Please set TAVILY_API_KEY, SERP_API_KEY, or BRAVE_SEARCH_API_KEY environment variable. DuckDuckGo is blocked."
