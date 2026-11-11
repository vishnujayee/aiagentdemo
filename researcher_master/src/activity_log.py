"""In-memory activity log for agent actions (discovery, ingest, verify, etc.) so the UI can show what the agent is doing."""
import time
from typing import List, Dict, Any

_MAX = 200
_events: List[Dict[str, Any]] = []


def log(agent: str, message: str, detail: Dict[str, Any] = None):
    entry = {
        "ts": time.time(),
        "agent": agent,
        "message": message,
        "detail": detail or {},
    }
    _events.append(entry)
    while len(_events) > _MAX:
        _events.pop(0)


def get_recent(limit: int = 80) -> List[Dict[str, Any]]:
    """Return most recent events (newest last)."""
    return list(_events[-limit:])
