"""Simple SQLite storage for chunks, KG nodes/edges, mappings and review queue.

This lightweight DB is for personal use and prototyping. It stores chunk metadata,
KG nodes and edges (as JSON), KG->chunk mappings, and the review queue.
"""
import sqlite3
import json
from typing import List, Dict, Any, Optional
import os


DB_PATH = os.getenv("STORAGE_DB_PATH", "./data/researcher_master.db")





def init_db(path: Optional[str] = None):
    p = path or DB_PATH
    os.makedirs(os.path.dirname(p), exist_ok=True)
    conn = sqlite3.connect(p)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS chunks (
        id TEXT PRIMARY KEY,
        doc_id TEXT,
        text TEXT,
        meta TEXT
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS kg_nodes (
        id TEXT PRIMARY KEY,
        node_json TEXT
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS kg_edges (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        edge_json TEXT
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS kg_mapping (
        node_label TEXT PRIMARY KEY,
        mapping_json TEXT
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS review_queue (
        idx INTEGER PRIMARY KEY AUTOINCREMENT,
        item_json TEXT
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS discovery_queue (
        id TEXT PRIMARY KEY,
        item_json TEXT
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS sandbox_runs (
        run_id TEXT PRIMARY KEY,
        run_json TEXT
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS schedules (
        name TEXT PRIMARY KEY,
        schedule_json TEXT
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS schedule_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        run_time TEXT,
        result_json TEXT
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS memory (
        id TEXT PRIMARY KEY,
        created TEXT,
        payload TEXT
    )
    """)
    conn.commit()
    conn.close()


def insert_chunk(chunk_id: str, doc_id: str, text: str, meta: Dict[str, Any]):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("REPLACE INTO chunks (id, doc_id, text, meta) VALUES (?, ?, ?, ?)",
                (chunk_id, doc_id, text, json.dumps(meta)))
    conn.commit()
    conn.close()


def get_chunks(limit: int = 100) -> List[Dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, doc_id, text, meta FROM chunks LIMIT ?", (limit,))
    rows = cur.fetchall()
    conn.close()
    return [{"id": r[0], "doc_id": r[1], "text": r[2], "meta": json.loads(r[3])} for r in rows]


def insert_kg_node(node_id: str, node: Dict[str, Any]):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("REPLACE INTO kg_nodes (id, node_json) VALUES (?, ?)", (node_id, json.dumps(node)))
    conn.commit()
    conn.close()


def insert_kg_edge(edge: Dict[str, Any]):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("INSERT INTO kg_edges (edge_json) VALUES (?)", (json.dumps(edge),))
    conn.commit()
    conn.close()


def save_mapping(node_label: str, mapping: Dict[str, Any]):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("REPLACE INTO kg_mapping (node_label, mapping_json) VALUES (?, ?)",
                (node_label, json.dumps(mapping)))
    conn.commit()
    conn.close()


def get_mapping(node_label: str) -> Optional[Dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT mapping_json FROM kg_mapping WHERE node_label = ?", (node_label,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return json.loads(row[0])


def enqueue_review(item: Dict[str, Any]):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("INSERT INTO review_queue (item_json) VALUES (?)", (json.dumps(item),))
    conn.commit()
    conn.close()


def get_review_queue() -> List[Dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT idx, item_json FROM review_queue ORDER BY idx ASC")
    rows = cur.fetchall()
    conn.close()
    return [{"idx": r[0], "item": json.loads(r[1])} for r in rows]


def remove_review(idx: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM review_queue WHERE idx = ?", (idx,))
    conn.commit()
    conn.close()


def save_discovery_candidate(candidate_id: str, item: Dict[str, Any]):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("REPLACE INTO discovery_queue (id, item_json) VALUES (?, ?)", (candidate_id, json.dumps(item)))
    conn.commit()
    conn.close()


def get_discovery_queue() -> List[Dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    try:
        cur.execute("SELECT id, item_json FROM discovery_queue")
        rows = cur.fetchall()
    except sqlite3.OperationalError as e:
        # likely the DB schema hasn't been created yet. Initialize and return empty queue.
        # This keeps callers resilient (they'll get an empty queue rather than crash).
        try:
            init_db(DB_PATH)
        except Exception:
            pass
        conn.close()
        return []
    conn.close()
    return [{"id": r[0], "item": json.loads(r[1])} for r in rows]


def remove_discovery_candidate(candidate_id: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM discovery_queue WHERE id = ?", (candidate_id,))
    conn.commit()
    conn.close()


def save_sandbox_run(run_id: str, record: Dict[str, Any]):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("REPLACE INTO sandbox_runs (run_id, run_json) VALUES (?, ?)", (run_id, json.dumps(record)))
    conn.commit()
    conn.close()


def get_sandbox_runs() -> List[Dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT run_id, run_json FROM sandbox_runs ORDER BY rowid DESC LIMIT 100")
    rows = cur.fetchall()
    conn.close()
    return [{"run_id": r[0], "record": json.loads(r[1])} for r in rows]


def save_schedule(name: str, schedule: Dict[str, Any]):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("REPLACE INTO schedules (name, schedule_json) VALUES (?, ?)", (name, json.dumps(schedule)))
    conn.commit()
    conn.close()


def get_schedules() -> List[Dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT name, schedule_json FROM schedules")
    rows = cur.fetchall()
    conn.close()
    return [{"name": r[0], "schedule": json.loads(r[1])} for r in rows]


def remove_schedule(name: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM schedules WHERE name = ?", (name,))
    conn.commit()
    conn.close()


def save_schedule_run(name: str, run_time: str, result: Dict[str, Any]):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("INSERT INTO schedule_runs (name, run_time, result_json) VALUES (?, ?, ?)", (name, run_time, json.dumps(result)))
    conn.commit()
    conn.close()


def get_schedule_runs(limit: int = 100) -> List[Dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, name, run_time, result_json FROM schedule_runs ORDER BY id DESC LIMIT ?", (limit,))
    rows = cur.fetchall()
    conn.close()
    return [{"id": r[0], "name": r[1], "run_time": r[2], "result": json.loads(r[3])} for r in rows]


# Ensure DB file and schema exist when the module is imported.
# This is defensive: if the DB file doesn't exist we create it and the tables.
try:
    if not os.path.exists(DB_PATH):
        init_db(DB_PATH)
except Exception:
    # best-effort only; specific functions will raise if something is wrong
    pass
