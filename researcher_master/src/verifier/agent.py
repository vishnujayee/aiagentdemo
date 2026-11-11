from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)


def verifier_agent(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Minimal verifier agent used by tests and local runs.

    - Uses the default retriever to search for supporting evidence.
    - Computes a simple confidence score and detects basic contradiction cues.
    - Enqueues low-confidence items to the review queue if available.
    """
    try:
        from src.rag.retriever import get_default_retriever
        from src.storage.db import enqueue_review
    except Exception as e:
        logger.exception(f"Verifier dependencies missing: {e}")
        return []

    retriever = get_default_retriever()
    results = []
    for it in items:
        text = it.get('text') or it.get('claim') or it.get('item', {}).get('text') or ''
        if not text:
            continue
        hits = retriever.search(text, top_k=5)
        if not hits:
            confidence = 0.0
        else:
            # normalize hit scores to 0..1 based on observed min/max among hits
            scores = [float(h.get('score', 0.0)) for h in hits]
            smin = min(scores)
            smax = max(scores)
            if smax > smin:
                norm = [(s - smin) / (smax - smin) for s in scores]
            else:
                # all hits equal score: if non-zero, treat as fully supported; else zero
                norm = [1.0 if s != 0.0 else 0.0 for s in scores]
            avg_score = sum(norm) / len(norm)
            doc_ids = set([h.get('meta', {}).get('doc_id') for h in hits if h.get('meta')])
            support_factor = min(5, len([d for d in doc_ids if d])) / 5.0
            confidence = 0.6 * avg_score + 0.4 * support_factor
        # clamp confidence to 0..1
        confidence = max(0.0, min(1.0, confidence))

        contradiction = False
        claim_lower = text.lower()
        negation_terms = ["not", "no ", "never", "none", "disprove", "contradict", "false", "incorrect", "does not"]
        contradiction_signals = []
        for h in hits:
            txt = (h.get('meta', {}).get('text') or h.get('meta', {}).get('snippet') or '').lower()
            for t in negation_terms:
                if t in txt and t not in claim_lower:
                    contradiction = True
                    contradiction_signals.append({"term": t, "evidence": txt[:300]})
                    break

        entry = {"item": it, "confidence": confidence, "evidence": hits, "contradiction": contradiction}
        if contradiction:
            entry["contradiction_signals"] = contradiction_signals
        results.append(entry)

        if confidence < 0.4:
            try:
                enqueue_review({"item": it, "reason": "low_confidence", "confidence": confidence})
            except Exception:
                logger.exception("Failed to enqueue review item")

    return results
