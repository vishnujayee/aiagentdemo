"""Simple Wikipedia fetcher using the MediaWiki API.

Provides a function to fetch plain-text extract for a given page title.
"""
import requests
from typing import Optional

WIKI_API = "https://en.wikipedia.org/w/api.php"


def fetch_wikipedia_page(title: str) -> Optional[str]:
    params = {
        "action": "query",
        "prop": "extracts",
        "explaintext": True,
        "titles": title,
        "format": "json",
        "redirects": 1,
    }
    resp = requests.get(WIKI_API, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    pages = data.get("query", {}).get("pages", {})
    for pid, page in pages.items():
        extract = page.get("extract")
        if extract:
            return extract
    return None
