"""Free web search via DuckDuckGo \u2014 no API key required."""
from duckduckgo_search import DDGS


def web_search(query: str, max_results: int = 5):
    with DDGS() as ddgs:
        results = list(ddgs.text(query, max_results=max_results))
    return [
        {
            "title": r.get("title", ""),
            "url": r.get("href", ""),
            "snippet": r.get("body", ""),
        }
        for r in results
    ]
