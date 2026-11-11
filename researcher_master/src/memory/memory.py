"""Simple memory module: short-term and long-term memory backed by SQLite.

Memory search uses lightweight lexical scoring and does not mutate the main RAG retriever.
"""
from typing import List, Dict, Any
import sqlite3
import json
import os
import re
from datetime import datetime

DB = os.getenv("STORAGE_DB_PATH", "./data/researcher_master.db")


def init_memory():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS memory (id TEXT PRIMARY KEY, created TEXT, payload TEXT)")
    conn.commit()
    conn.close()


def add_memory(mem_id: str, payload: Dict[str, Any]):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute(
        "REPLACE INTO memory (id, created, payload) VALUES (?, ?, ?)",
        (mem_id, datetime.utcnow().isoformat(), json.dumps(payload)),
    )
    conn.commit()
    conn.close()


def get_all_memory(limit: int = 100) -> List[Dict[str, Any]]:
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT id, created, payload FROM memory ORDER BY created DESC LIMIT ?", (limit,))
    rows = cur.fetchall()
    conn.close()
    return [{"id": r[0], "created": r[1], "payload": json.loads(r[2])} for r in rows]


def _tokenize(text: str) -> List[str]:
    return re.findall(r"\w+", (text or "").lower())


def query_memory(query: str, top_k: int = 5) -> List[Dict[str, Any]]:
    """Lexical search over memory payloads without altering global retrieval state."""
    q_tokens = set(_tokenize(query))
    if not q_tokens:
        return []

    items = get_all_memory(limit=1000)
    scored = []
    for it in items:
        payload = it.get("payload", {})
        text = json.dumps(payload, ensure_ascii=False) if isinstance(payload, dict) else str(payload)
        t_tokens = set(_tokenize(text))
        if not t_tokens:
            continue
        overlap = len(q_tokens & t_tokens)
        if overlap == 0:
            continue
        score = overlap / max(len(q_tokens), 1)
        scored.append(
            {
                "score": float(score),
                "meta": {
                    "doc_id": it.get("id"),
                    "meta": {"created": it.get("created"), "source": "memory"},
                    "text": text,
                },
                "idx": len(scored),
            }
        )

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[: max(1, int(top_k))]
