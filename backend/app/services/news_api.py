"""
news_api.py - Fetches real financial news from NewsAPI.org
"""

import os
import httpx

NEWS_API_KEY = os.getenv("NEWS_API_KEY", "")
NEWS_API_BASE = "https://newsapi.org/v2"


async def fetch_news(query: str, category: str = "business", language: str = "en", page_size: int = 5) -> list[dict]:
    if not NEWS_API_KEY:
        return [{"title": "NewsAPI key not configured", "description": "Set NEWS_API_KEY in .env", "source": "system"}]
    articles = await _search_news(query, language, page_size)
    if not articles:
        articles = await _top_headlines(category, language, page_size)
    return articles


async def _search_news(query, language, page_size):
    params = {"q": query, "language": language, "pageSize": page_size, "sortBy": "publishedAt", "apiKey": NEWS_API_KEY}
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            resp = await client.get(f"{NEWS_API_BASE}/everything", params=params)
            resp.raise_for_status()
            return _simplify(resp.json().get("articles", []))
        except Exception:
            return []


async def _top_headlines(category, language, page_size):
    params = {"category": category, "language": language, "pageSize": page_size, "apiKey": NEWS_API_KEY}
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            resp = await client.get(f"{NEWS_API_BASE}/top-headlines", params=params)
            resp.raise_for_status()
            return _simplify(resp.json().get("articles", []))
        except Exception:
            return []


def _simplify(articles):
    return [{"title": a.get("title", ""), "description": a.get("description", ""), "source": a.get("source", {}).get("name", ""), "published_at": a.get("publishedAt", ""), "url": a.get("url", "")} for a in articles]
