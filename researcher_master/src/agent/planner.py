"""Simple planner and executor for autonomous agent runs.

This module uses the local LLM fallback to decompose a high-level goal into steps,
then executes safe, well-known actions via the Orchestrator (search, ingest, verify).
It records step results into the memory store for traceability.
"""
from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)


def execute_step(step: str, orchestrator) -> Dict[str, Any]:
    """Execute a single step string using orchestrator actions.

    Supported step forms (naive):
    - "search: <query>" -> orchestrator.run_agent('discovery', [query])
    - "ingest: <doc-id>|<text>" -> orchestrator.run_agent('ingest', [doc])
    - "verify: <claim>" -> orchestrator.run_agent('verifier', [{'text': claim}])
    - otherwise: returns a note that the step was skipped.
    """
    step = step.strip()
    try:
        if step.lower().startswith('search:'):
            q = step.split(':', 1)[1].strip()
            # discovery agent expects seeds list
            res = orchestrator.run_agent('discovery', [q])
            return {'action': 'search', 'query': q, 'result': res}

        if step.lower().startswith('ingest:'):
            payload = step.split(':', 1)[1].strip()
            # simple notation: id|text
            if '|' in payload:
                doc_id, text = payload.split('|', 1)
                doc = {'id': doc_id.strip(), 'text': text.strip(), 'meta': {'source': 'planner'}}
            else:
                doc = {'id': None, 'text': payload, 'meta': {'source': 'planner'}}
            res = orchestrator.run_agent('ingest', [doc])
            return {'action': 'ingest', 'doc': doc, 'result': res}

        if step.lower().startswith('verify:'):
            claim = step.split(':', 1)[1].strip()
            res = orchestrator.run_agent('verifier', [{'text': claim}])
            return {'action': 'verify', 'claim': claim, 'result': res}

        return {'action': 'skip', 'note': f'Unrecognized step: {step}'}
    except Exception as e:
        logger.exception(f"Failed executing step '{step}': {e}")
        return {'action': 'error', 'step': step, 'error': str(e)}


def generate_and_execute(goal: str, max_steps: int = 10) -> Dict[str, Any]:
    """Generate plan using local LLM and execute safe steps via orchestrator.

    Returns a run log with steps, step_results, and a final summary.
    """
    from src.llm.llm import get_default_llm
    from src.memory.memory import add_memory
    try:
        from src.orchestrator import orchestrator
    except Exception:
        import importlib
        mod = importlib.import_module('src.orchestrator')
        orchestrator = getattr(mod, 'orchestrator', mod)

    llm = get_default_llm()
    plan_steps = llm.plan(goal)
    # limit steps
    steps = plan_steps[:max_steps]
    results = []
    for s in steps:
        r = execute_step(s, orchestrator)
        results.append({'step': s, 'result': r})
        # persist step outcome to memory for later recall
        try:
            mem_id = f"plan:{goal}:{len(results)}"
            add_memory(mem_id, {'goal': goal, 'step': s, 'result': r})
        except Exception:
            logger.exception("Failed to save memory for step")

    summary = {'goal': goal, 'steps_executed': len(results), 'results': results}
    return summary
