"""Continuous autonomy manager.

Runs a conservative autonomous loop for a single goal: generate plan, execute steps
via the orchestrator, run verification on results, reflect (summarize) and store
outcomes to memory. Designed to work with lexical fallbacks so it runs without
heavy ML dependencies.
"""
import threading
import time
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class AutonomyManager:
    def __init__(self):
        self._thread: Optional[threading.Thread] = None
        self._stop_flag = False
        self._status: Dict[str, Any] = {"running": False, "goal": None, "last_run": None}

    def start(self, goal: str, loop_interval: int = 60):
        if self._thread and self._thread.is_alive():
            logger.info("Autonomy manager already running")
            return False

        self._stop_flag = False
        self._status.update({"running": True, "goal": goal, "loop_interval": loop_interval})

        def _loop():
            logger.info(f"Autonomy loop started for goal: {goal}")
            from src.agent.planner import generate_and_execute
            from src.orchestrator import orchestrator
            from src.rag.rag import answer_question
            from src.memory.memory import add_memory
            from src.llm.llm import get_default_llm

            llm = get_default_llm()

            while not self._stop_flag:
                try:
                    # Generate and execute plan (planner persists step outcomes)
                    run_result = generate_and_execute(goal, max_steps=6)

                    # run verifier on any claimed findings: extract any 'claim' or ingested texts
                    try:
                        verifier_items = []
                        for entry in run_result.get('results', []):
                            r = entry.get('result', {})
                            if r.get('action') == 'verify' and r.get('claim'):
                                verifier_items.append({'text': r.get('claim')})
                            if r.get('action') == 'ingest' and r.get('doc'):
                                # verify the doc text briefly
                                d = r.get('doc')
                                if isinstance(d, dict) and d.get('text'):
                                    verifier_items.append({'text': d.get('text')})
                        if verifier_items:
                            try:
                                vres = orchestrator.run_agent('verifier', verifier_items)
                                # if verifier enqueues low-confidence items, that is handled by verifier
                            except Exception:
                                logger.exception('Verifier run failed')
                    except Exception:
                        logger.exception('Failed to assemble verifier items')

                    # run reflection / summarization
                    mem_summary = f"Executed plan with {len(run_result.get('results', []))} steps"
                    prompt = f"Summarize the run results and next actions for goal: {goal}\nResults: {run_result}\nGive 3 next-step suggestions."
                    refl = llm.generate(prompt, max_tokens=256)

                    # persist run summary to memory
                    try:
                        mem_id = f"autonomy:{int(time.time())}"
                        add_memory(mem_id, {"goal": goal, "run": run_result, "reflection": refl})
                    except Exception:
                        logger.exception("Failed to save autonomy run to memory")

                    # update status
                    self._status.update({"last_run": time.time(), "last_result": run_result, "last_reflection": refl})
                except Exception as e:
                    logger.exception(f"Autonomy loop error: {e}")

                # wait until next cycle or stop
                for _ in range(int(loop_interval)):
                    if self._stop_flag:
                        break
                    time.sleep(1)

            logger.info("Autonomy loop stopped")
            self._status.update({"running": False})

        t = threading.Thread(target=_loop, daemon=True)
        t.start()
        self._thread = t
        return True

    def stop(self):
        self._stop_flag = True
        return True

    def status(self):
        return self._status


# singleton manager
manager = AutonomyManager()
"""Continuous learning manager: small, local-first cycle runner.

This module implements a conservative, auditable cycle:
- run discovery for configured seeds
- verify discovered candidates
- auto-ingest high-confidence items
- leave low-confidence items in the review queue for humans

Designed to be simple so it can run locally or be scheduled by the Orchestrator.
"""
from typing import List
import os
import logging

logger = logging.getLogger(__name__)


def run_cycle(seeds: List[str] = None, verify_threshold: float = 0.5):
    """Run one discovery->verify->ingest cycle.

    seeds: list of seed queries for discovery. If None, attempts to read
    DISCOVERY_SEEDS env var (comma-separated). Returns a summary dict.
    """
    try:
        # Prefer to import the orchestrator instance, but tests sometimes inject a module
        # object into sys.modules['src.orchestrator'] directly. Be flexible:
        try:
            from src.orchestrator import orchestrator
        except Exception:
            import importlib
            mod = importlib.import_module('src.orchestrator')
            # if the module itself implements run_agent, treat it as the orchestrator
            if hasattr(mod, 'run_agent'):
                orchestrator = mod
            else:
                # re-raise original import error
                raise

        from src.storage.db import get_discovery_queue, remove_discovery_candidate
        from src.storage.db import enqueue_review
        from src.safety.policy import is_allowed_url
    except Exception as e:
        logger.exception(f"Missing dependencies for continuous manager: {e}")
        raise

    seeds = seeds or os.getenv("DISCOVERY_SEEDS", "wikipedia:machine learning,arXiv:AI").split(',')
    seeds = [s.strip() for s in seeds if s and s.strip()]

    logger.info(f"Running continuous cycle with seeds: {seeds}")
    # run discovery
    try:
        orchestrator.run_agent('discovery', seeds)
    except Exception as e:
        logger.exception(f"Discovery agent failed: {e}")

    # snapshot discovery queue
    queue = get_discovery_queue()
    accepted = []
    deferred = []

    for item in queue:
        candidate = item.get('item') if isinstance(item.get('item'), dict) else item
        # simple normalization of candidate
        url = candidate.get('url') or candidate.get('meta', {}).get('url')
        if url and not is_allowed_url(url):
            logger.info(f"Rejecting candidate due to policy: {url}")
            # remove and skip
            try:
                remove_discovery_candidate(item.get('id') or candidate.get('id'))
            except Exception:
                pass
            continue

        # run verifier on this candidate
        try:
            res = orchestrator.run_agent('verifier', [candidate])
        except Exception as e:
            logger.exception(f"Verifier failed for candidate: {e}")
            deferred.append(candidate)
            continue

        # res is a list of per-item results
        r = res[0] if res and isinstance(res, list) else None
        confidence = r.get('confidence') if r else 0.0
        contradiction = r.get('contradiction') if r else False

        if contradiction or confidence < verify_threshold:
            logger.info(f"Deferring candidate for human review (conf={confidence}, contrad={contradiction})")
            deferred.append(candidate)
            # leave in queue for manual review
            try:
                enqueue_review({"item": candidate, "reason": "deferred_by_cycle", "confidence": confidence})
            except Exception:
                pass
        else:
            # auto-ingest
            logger.info(f"Auto-ingesting candidate (conf={confidence}): {candidate.get('url')}")
            try:
                orchestrator.run_agent('ingest', [candidate])
                accepted.append(candidate)
                # remove from discovery queue
                try:
                    remove_discovery_candidate(item.get('id') or candidate.get('id'))
                except Exception:
                    pass
            except Exception as e:
                logger.exception(f"Failed to ingest candidate: {e}")
                deferred.append(candidate)

    summary = {"accepted": len(accepted), "deferred": len(deferred), "queue_snapshot": len(queue)}
    logger.info(f"Cycle complete: {summary}")
    return summary


if __name__ == '__main__':
    import sys
    seeds = sys.argv[1:] if len(sys.argv) > 1 else None
    print(run_cycle(seeds=seeds))
