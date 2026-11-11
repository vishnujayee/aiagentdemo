"""Learner utilities: fetch content and add to discovery/ingest pipeline."""
from typing import Optional, Dict, Any
import requests
import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def fetch_url_text(url: str, timeout: int = 10) -> Optional[str]:
    try:
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
        # naive extraction: return full HTML body text; callers can refine
        return resp.text
    except Exception as e:
        logger.exception(f"Failed to fetch URL {url}: {e}")
        return None


def learn_from_url(url: str, ingest_immediately: bool = True) -> Dict[str, Any]:
    """Fetch URL, create a candidate, and either enqueue for discovery or ingest directly.

    Returns a summary dict with status and id.
    """
    txt = fetch_url_text(url)
    if not txt:
        return {"status": "failed", "reason": "fetch_failed"}

    # create candidate
    cid = url
    candidate = {"id": cid, "text": txt, "meta": {"url": url, "source": urlparse(url).netloc}}
    try:
        from src.orchestrator import orchestrator
        if ingest_immediately:
            orchestrator.run_agent('ingest', [candidate])
            return {"status": "ingested", "id": cid}
        else:
            from src.storage.db import save_discovery_candidate
            save_discovery_candidate(cid, candidate)
            return {"status": "enqueued", "id": cid}
    except Exception as e:
        logger.exception(f"Learner failed to hand off candidate: {e}")
        return {"status": "failed", "reason": str(e)}


def learn_from_text(text: str, doc_id: str = None, ingest_immediately: bool = True) -> Dict[str, Any]:
    cid = doc_id or f"text:{hash(text)}"
    candidate = {"id": cid, "text": text, "meta": {"source": "direct"}}
    try:
        from src.orchestrator import orchestrator
        if ingest_immediately:
            orchestrator.run_agent('ingest', [candidate])
            return {"status": "ingested", "id": cid}
        else:
            from src.storage.db import save_discovery_candidate
            save_discovery_candidate(cid, candidate)
            return {"status": "enqueued", "id": cid}
    except Exception as e:
        logger.exception(f"Learner failed to hand off candidate: {e}")
        return {"status": "failed", "reason": str(e)}
