from duckduckgo_search import DDGS


def web_search(query: str, max_results: int = 6) -> list[dict]:
    with DDGS() as d:
        results = list(d.text(query, max_results=max_results))
    return [
        {"title": r.get("title", ""), "url": r.get("href", ""), "snippet": r.get("body", "")}
        for r in results
    ]
