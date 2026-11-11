"""Minimal safety and policy checks for discovery/ingest.

This module implements very small, conservative checks:
- domain denylist
- simple filetype and scheme checks

These are NOT a substitute for legal review or a hardened policy engine.
"""
from urllib.parse import urlparse
import re

# very conservative domain denylist (examples)
_DENY_DOMAINS = [
    r".*\.example\.com$",
]


def is_allowed_url(url: str) -> bool:
    if not url:
        return False
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False
    host = parsed.hostname or ""
    for pat in _DENY_DOMAINS:
        if re.match(pat, host):
            return False
    # block common binary filetypes in discovery by path
    path = parsed.path.lower()
    if path.endswith(('.exe', '.zip', '.bin', '.deb', '.iso')):
        return False
    return True


if __name__ == '__main__':
    tests = [
        'https://en.wikipedia.org/wiki/Photosynthesis',
    ]
    for t in tests:
        print(t, is_allowed_url(t))
