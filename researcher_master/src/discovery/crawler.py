"""Polite crawler helper used by discovery adapters.

Provides robots.txt caching and per-host politeness delays.
"""
from urllib.parse import urlparse, urljoin
import urllib.request
import urllib.robotparser
import time
import threading

_robots_cache = {}
_last_access = {}
_lock = threading.Lock()


def fetch_with_robots(url: str, user_agent: str = 'researcher-master-bot', timeout: int = 10):
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    rp = _robots_cache.get(base)
    if not rp:
        rp = urllib.robotparser.RobotFileParser()
        try:
            rp.set_url(urljoin(base, '/robots.txt'))
            rp.read()
        except Exception:
            # failed to read robots; default to allow
            rp = None
        _robots_cache[base] = rp

    if rp and not rp.can_fetch(user_agent, url):
        raise PermissionError(f"Blocked by robots.txt: {url}")

    # politeness: simple per-host delay (default 1s)
    wait = 1.0
    with _lock:
        last = _last_access.get(base)
        if last:
            delta = time.time() - last
            if delta < wait:
                time.sleep(wait - delta)
        _last_access[base] = time.time()

    req = urllib.request.Request(url, headers={"User-Agent": user_agent})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        content_type = resp.headers.get('Content-Type', '')
        body = resp.read()
        return {'url': url, 'content_type': content_type, 'body': body}
