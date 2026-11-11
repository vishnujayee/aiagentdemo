"""Discovery adapters: search APIs and simple fallbacks.

Provides a small interface to discover candidate documents given seed queries.
Supports SerpAPI (if SERPAPI_API_KEY provided), optional DuckDuckGo, and Wikipedia fallback.
"""
import os
import re
import requests
import uuid
import time
import urllib.robotparser
from urllib.parse import urlparse, quote_plus
from typing import List, Dict

# simple in-memory robots.txt and per-host rate limiter caches
_robots_cache: Dict[str, urllib.robotparser.RobotFileParser] = {}
_last_access: Dict[str, float] = {}
# No heavy restriction: fast crawl by default; set DEFAULT_CRAWL_DELAY=2.0 for politeness
DEFAULT_CRAWL_DELAY = float(os.getenv("DEFAULT_CRAWL_DELAY", "0.5"))
CRAWL_MAX_RESULTS = int(os.getenv("CRAWL_MAX_RESULTS", "50"))


SERPAPI_KEY = os.getenv("SERPAPI_API_KEY")
USE_DUCKDUCKGO = os.getenv("USE_DUCKDUCKGO", "1").lower() in ("1", "true", "yes")


def fetch_wikipedia_page(title: str) -> str:
    # lightweight wrapper to fetch page content via MediaWiki
    S = requests.Session()
    URL = "https://en.wikipedia.org/w/api.php"
    params = {
        "action": "query",
        "prop": "extracts",
        "explaintext": True,
        "titles": title,
        "format": "json",
    }
    r = S.get(URL, params=params, timeout=15)
    r.raise_for_status()
    data = r.json()
    pages = data.get("query", {}).get("pages", {})
    if not pages:
        return ""
    page = next(iter(pages.values()))
    return page.get("extract", "")


def wikipedia_suggest_title(query: str) -> str:
    """Return best matching Wikipedia title for a free-text query."""
    try:
        r = requests.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "opensearch",
                "search": query,
                "limit": 1,
                "namespace": 0,
                "format": "json",
            },
            timeout=12,
        )
        r.raise_for_status()
        data = r.json()
        titles = data[1] if isinstance(data, list) and len(data) > 1 else []
        return titles[0] if titles else ""
    except Exception:
        return ""


def serpapi_search(query: str, num: int = 5) -> List[Dict]:
    if not SERPAPI_KEY:
        return []
    params = {
        "engine": "google",
        "q": query,
        "api_key": SERPAPI_KEY,
        "num": num,
    }
    r = requests.get("https://serpapi.com/search", params=params, timeout=15)
    r.raise_for_status()
    data = r.json()
    results = []
    for item in data.get("organic_results", [])[:num]:
        results.append({
            "url": item.get("link"),
            "title": item.get("title"),
            "snippet": item.get("snippet"),
            "source": "serpapi",
        })
    return results


def duckduckgo_search(query: str, num: int = 5) -> List[Dict]:
    """DuckDuckGo HTML search (no API key). Returns list of {url, title, snippet}."""
    try:
        from ddgs import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=num))
        return [
            {"url": r.get("href") or r.get("link"), "title": r.get("title", ""), "snippet": r.get("body", ""), "source": "duckduckgo"}
            for r in results
        ]
    except Exception:
        pass
    # Fallback: request DDG HTML and parse (fragile but no extra dep)
    if not USE_DUCKDUCKGO:
        return []
    try:
        url = "https://html.duckduckgo.com/html/?q=" + quote_plus(query)
        r = requests.get(url, timeout=12, headers={"User-Agent": "ResearcherMasterBot/0.1"})
        r.raise_for_status()
        html = r.text
        # parse .result__a links and .result__snippet
        links = re.findall(r'class="result__a"[^>]*href="([^"]+)"[^>]*>([^<]+)</a>', html)
        snippets = re.findall(r'class="result__snippet"[^>]*>([^<]+)', html)
        results = []
        for i, (href, title) in enumerate(links[:num]):
            if href.startswith("//"):
                href = "https:" + href
            elif href.startswith("/"):
                href = "https://duckduckgo.com" + href
            results.append({"url": href, "title": title.strip(), "snippet": (snippets[i] if i < len(snippets) else "").strip(), "source": "duckduckgo"})
        return results
    except Exception:
        return []


def fetch_url_text(url: str) -> str:
    try:
        # Respect robots.txt for the domain, cache parser per host
        parsed = urlparse(url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        rp = _robots_cache.get(base)
        if rp is None:
            rp = urllib.robotparser.RobotFileParser()
            try:
                rp.set_url(base + "/robots.txt")
                rp.read()
            except Exception:
                # leave parser but it may disallow everything by default
                pass
            _robots_cache[base] = rp

        try:
            if not rp.can_fetch("ResearcherMasterBot", url):
                return ""
        except Exception:
            pass

        # per-host politeness: ensure minimal gap between requests
        last = _last_access.get(parsed.netloc, 0.0)
        gap = DEFAULT_CRAWL_DELAY
        now = time.time()
        wait = gap - (now - last)
        if wait > 0:
            time.sleep(wait)
        _last_access[parsed.netloc] = time.time()

        r = requests.get(url, timeout=15, headers={"User-Agent": "ResearcherMasterBot/0.1"})
        r.raise_for_status()
        text = r.text
        # very lightweight html tag stripper
        import re
        s = re.sub(r"<script.*?>.*?</script>", "", text, flags=re.S)
        s = re.sub(r"<style.*?>.*?</style>", "", s, flags=re.S)
        s = re.sub(r"<[^>]+>", "\n", s)
        s = re.sub(r"\s+", " ", s)
        return s.strip()
    except Exception:
        return ""


def discover_from_seeds(seed_queries: List[str], provider: str = "auto", max_results: int = None) -> List[Dict]:
    """Return a list of candidate documents with keys: url, title, snippet, text, id.
    Uses SerpAPI (if key set), then DuckDuckGo (if enabled), then Wikipedia.
    No artificial limit on crawl depth; use CRAWL_MAX_RESULTS env to cap per-query results.
    """
    if max_results is None:
        max_results = CRAWL_MAX_RESULTS
    candidates = []
    for q in seed_queries:
        # 1) SerpAPI when available
        if provider in ("auto", "serpapi") and SERPAPI_KEY:
            try:
                items = serpapi_search(q, num=max_results)
                for it in items:
                    url = it.get("url")
                    text = fetch_url_text(url) if url else it.get("snippet")
                    candidates.append({"id": str(uuid.uuid4()), "url": url, "title": it.get("title"), "snippet": it.get("snippet"), "text": text or it.get("snippet"), "source": "web"})
                continue
            except Exception:
                pass

        # 2) DuckDuckGo (search engine, no API key required)
        if provider in ("auto", "duckduckgo", "search") and USE_DUCKDUCKGO:
            try:
                items = duckduckgo_search(q, num=max_results)
                added = 0
                for it in items:
                    url = it.get("url")
                    text = fetch_url_text(url) if url else it.get("snippet")
                    candidates.append({"id": str(uuid.uuid4()), "url": url, "title": it.get("title"), "snippet": it.get("snippet"), "text": text or it.get("snippet"), "source": "web"})
                    added += 1
                if added:
                    continue
            except Exception:
                pass

        # 3) Wikipedia fallback (exact title -> suggested title)
        try:
            text = fetch_wikipedia_page(q)
            title = q
            if not text:
                suggested = wikipedia_suggest_title(q)
                if suggested:
                    text = fetch_wikipedia_page(suggested)
                    title = suggested
            if text:
                candidates.append({"id": str(uuid.uuid4()), "url": f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}", "title": title, "snippet": text[:300], "text": text, "source": "wikipedia"})
        except Exception:
            continue

    # Last-resort local fallback so worker/ingest flows remain functional offline.
    if not candidates:
        for q in seed_queries:
            text = (
                f"Seed topic: {q}. "
                f"No external source was reachable at discovery time. "
                f"This placeholder keeps the autonomous ingest/worker loop active."
            )
            candidates.append(
                {
                    "id": str(uuid.uuid4()),
                    "url": f"local://seed/{quote_plus(q)}",
                    "title": q,
                    "snippet": text[:300],
                    "text": text,
                    "source": "local_seed",
                }
            )

    # persist candidates into discovery queue if db available
    try:
        from src.storage.db import save_discovery_candidate
        for c in candidates:
            cid = c.get("id") or str(uuid.uuid4())
            try:
                # persist the raw candidate dict for review
                save_discovery_candidate(cid, c)
            except Exception:
                pass
    except Exception:
        pass

    return candidates

