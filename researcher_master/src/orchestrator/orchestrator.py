"""Orchestrator skeleton for coordinating specialist agents.

This provides a simple, extensible class where agents (functions or callables)
can be registered and invoked. It includes simple scheduling and a discovery
pipeline placeholder that you can extend.
"""
import threading
import time
from typing import Callable, Dict, Any, List
import logging
import uuid

logger = logging.getLogger(__name__)


class Orchestrator:
    def __init__(self):
        self.agents: Dict[str, Callable[..., Any]] = {}
        self.running = False
        self.schedule: List[Dict[str, Any]] = []
        self._workers: Dict[str, Dict] = {}
        # load persisted schedules from DB (best-effort)
        try:
            from src.storage.db import get_schedules
            for s in get_schedules():
                sched = s.get("schedule", {})
                if sched:
                    self.schedule.append(sched)
        except Exception:
            # if DB not ready, ignore
            pass

    def register_agent(self, name: str, fn: Callable[..., Any]):
        self.agents[name] = fn
        logger.info(f"Registered agent: {name}")

    def run_agent(self, name: str, *args, **kwargs):
        fn = self.agents.get(name)
        if not fn:
            raise ValueError(f"Agent {name} not registered")
        logger.info(f"Running agent: {name}")
        return fn(*args, **kwargs)

    def schedule_agent(self, name: str, interval_seconds: int, args=(), kwargs=None):
        job = {"name": name, "interval": interval_seconds, "args": args, "kwargs": kwargs or {}}
        self.schedule.append(job)
        # persist schedule to DB so it survives restarts
        try:
            from src.storage.db import save_schedule
            save_schedule(f"{name}:{len(self.schedule)}", job)
        except Exception:
            pass

    def list_schedules(self) -> List[Dict[str, Any]]:
        return self.schedule

    def remove_schedule(self, name: str):
        # remove by name match
        self.schedule = [s for s in self.schedule if s.get("name") != name]
        try:
            from src.storage.db import remove_schedule
            remove_schedule(name)
        except Exception:
            pass

    def _runner_loop(self):
        # simple scheduler loop: runs each agent once per interval
        next_run = {s["name"]: time.time() for s in self.schedule}
        while self.running:
            now = time.time()
            for s in self.schedule:
                name = s["name"]
                if now >= next_run[name]:
                    try:
                        res = self.run_agent(name, *s.get("args", ()), **s.get("kwargs", {}))
                        # persist run result to DB (best-effort)
                        try:
                            from datetime import datetime
                            from src.storage.db import save_schedule_run
                            save_schedule_run(name, datetime.utcnow().isoformat(), {"result": res})
                        except Exception:
                            pass
                    except Exception as e:
                        logger.exception(f"Agent {name} failed: {e}")
                    next_run[name] = now + s["interval"]
            time.sleep(1)

    def start(self):
        if self.running:
            return
        self.running = True
        t = threading.Thread(target=self._runner_loop, daemon=True)
        t.start()
        logger.info("Orchestrator started")

    # Simple worker management: workers poll a queue and process items.
    def start_worker(self, worker_name: str = 'discovery_worker', poll_interval: int = 5):
        if worker_name in self._workers:
            logger.info(f"Worker {worker_name} already running")
            return

        stop_flag = {'stop': False}

        def _worker_loop():
            logger.info(f"Worker {worker_name} started, polling discovery queue every {poll_interval}s")
            from src.storage.db import get_discovery_queue, remove_discovery_candidate
            while not stop_flag['stop']:
                try:
                    q = get_discovery_queue()
                    for item in q:
                        # robustly extract candidate
                        candidate = item.get('item') if isinstance(item.get('item'), dict) else item.get('item') or item
                        try:
                            # call ingest_agent to process candidate
                            ingest_agent([candidate])
                        except Exception:
                            logger.exception('Failed to ingest discovery candidate')
                        try:
                            remove_discovery_candidate(item.get('id'))
                        except Exception:
                            # try removing by nested id
                            try:
                                remove_discovery_candidate(candidate.get('id'))
                            except Exception:
                                pass
                    time.sleep(poll_interval)
                except Exception:
                    logger.exception('Worker loop encountered error; continuing')
                    time.sleep(poll_interval)
            logger.info(f"Worker {worker_name} stopped")

        t = threading.Thread(target=_worker_loop, daemon=True)
        t.start()
        self._workers[worker_name] = {'thread': t, 'stop_flag': stop_flag}

    def stop_worker(self, worker_name: str):
        w = self._workers.get(worker_name)
        if not w:
            logger.info(f"Worker {worker_name} not found")
            return
        try:
            w['stop_flag']['stop'] = True
        except Exception:
            pass
        # let thread exit; remove from dict
        self._workers.pop(worker_name, None)
        logger.info(f"Requested stop for worker {worker_name}")

    def stop(self):
        self.running = False
        logger.info("Orchestrator stopped")


def _activity(agent: str, message: str, detail: dict = None):
    try:
        from src.activity_log import log
        log(agent, message, detail)
    except Exception:
        pass


# Example stub agents you can wire in the project
def discovery_agent(seed_queries: List[str]):
    """Run discovery using the discovery adapters and return discovered docs.

    This will fetch candidate documents and hand them to the ingest pipeline.
    """
    logger.info(f"Discovery agent running for seeds: {seed_queries}")
    _activity("discovery", "Crawling & searching", {"seeds": seed_queries})
    try:
        from src.discovery.search import discover_from_seeds
    except Exception as e:
        logger.exception(f"Discovery module not available: {e}")
        _activity("discovery", "Discovery failed", {"error": str(e)})
        return []

    candidates = discover_from_seeds(seed_queries)
    logger.info(f"Discovery found {len(candidates)} candidates")
    _activity("discovery", f"Found {len(candidates)} sources", {"count": len(candidates), "seeds": seed_queries})
    # hand off to ingest agent
    try:
        ingest_agent(candidates)
    except Exception:
        logger.exception("Failed to hand off candidates to ingest_agent")
    return candidates


def ingest_agent(documents: List[Dict[str, Any]]):
    """Ingest documents: chunk them and add to the retriever index.

    documents: list of {id, text, meta}
    """
    logger.info(f"Ingesting {len(documents)} docs")
    _activity("ingest", f"Ingesting {len(documents)} documents", {"count": len(documents)})
    try:
        from src.ingest.ingest import ingest_text_chunks
        from src.rag.retriever import get_default_retriever
    except Exception as e:
        logger.exception(f"Ingest dependencies missing: {e}")
        _activity("ingest", "Ingest failed", {"error": str(e)})
        return False

    all_chunks = []
    for doc in documents:
        doc_id = doc.get("id") or str(uuid.uuid4())
        text = doc.get("text") or doc.get("snippet", "")
        meta = doc.get("meta") or {"source": doc.get("source"), "url": doc.get("url"), "title": doc.get("title")}
        # ingest_text_chunks returns list of tuples (chunk_id, chunk_text, meta)
        chunks = ingest_text_chunks(text, metadata={**meta, "doc_id": doc_id})
        all_chunks.extend(chunks)

    if not all_chunks:
        logger.info("No chunks produced; aborting index build")
        _activity("ingest", "No chunks produced", {})
        return False

    retriever = get_default_retriever()
    retriever.build_index(all_chunks)
    try:
        retriever.save()
    except Exception:
        logger.exception("Failed to save retriever index")
    _activity("ingest", f"Index updated: {len(all_chunks)} chunks", {"chunks": len(all_chunks)})
    logger.info("Ingest complete: index built/updated")
    return True


def verifier_agent(items: List[Dict[str, Any]]):
    """Basic verifier: for each item (expected to have 'text' or 'claim'),
    run retrieval to find supporting passages and compute a simple confidence.
    Low-confidence items are enqueued to the review queue.
    """
    logger.info(f"Verifier checking {len(items)} items")
    _activity("verifier", f"Verifying {len(items)} claims", {"count": len(items)})
    try:
        from src.rag.retriever import get_default_retriever
        from src.storage.db import enqueue_review
    except Exception as e:
        logger.exception(f"Verifier dependencies missing: {e}")
        return []

    retriever = get_default_retriever()
    results = []
    for it in items:
        text = it.get("text") or it.get("claim") or it.get("item", {}).get("text") or ""
        if not text:
            continue
        hits = retriever.search(text, top_k=5)
        # compute confidence: consider number of distinct sources and average score
        if not hits:
            confidence = 0.0
        else:
            avg_score = sum([h.get("score", 0.0) for h in hits]) / len(hits)
            # count distinct doc_ids among evidence
            doc_ids = set([h.get("meta", {}).get("doc_id") for h in hits if h.get("meta")])
            source_support = len([d for d in doc_ids if d])
            # simple heuristic: normalize source_support (cap at 5)
            support_factor = min(5, source_support) / 5.0
            confidence = 0.6 * avg_score + 0.4 * support_factor

        entry = {"item": it, "confidence": confidence, "evidence": hits}
        # contradiction detection: simple heuristic looking for negation/contradictory phrases
        contradiction = False
        claim_lower = text.lower()
        negation_terms = ["not", "no ", "never", "none", "disprove", "contradict", "false", "incorrect", "does not"]
        contradiction_signals = []
        for h in hits:
            txt = (h.get("meta", {}).get("text") or h.get("meta", {}).get("snippet") or "").lower()
            # look for explicit contradiction cues
            for t in negation_terms:
                if t in txt and t not in claim_lower:
                    contradiction = True
                    contradiction_signals.append({"term": t, "evidence": txt[:300]})
                    break

        entry["contradiction"] = contradiction
        if contradiction:
            entry["contradiction_signals"] = contradiction_signals
        results.append(entry)
        # enqueue to review if low confidence
        if confidence < 0.4:
            try:
                enqueue_review({"item": it, "reason": "low_confidence", "confidence": confidence})
            except Exception:
                logger.exception("Failed to enqueue review item")

    return results
