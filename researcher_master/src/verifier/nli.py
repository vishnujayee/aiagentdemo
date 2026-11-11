import re
from typing import Dict


def predict_entailment(premise: str, hypothesis: str) -> Dict[str, float]:
    """Lightweight, lexical fallback for entailment.

    - Computes token overlap ratio (how many hypothesis tokens appear in premise).
    - If a negation mismatch is detected (crude), returns CONTRADICTION.
    - Otherwise returns ENTAILMENT when overlap is high, NEUTRAL otherwise.
    This is intentionally simple and deterministic for local-first runs and tests.
    """
    def tokens(s: str):
        return set(re.findall(r"\w+", (s or "").lower()))

    p_t = tokens(premise)
    h_t = tokens(hypothesis)
    if not h_t:
        return {"label": "NEUTRAL", "score": 0.0}

    overlap = p_t & h_t
    score = float(len(overlap) / len(h_t))

    # crude negation check
    neg = {'not', "n't", 'never', 'no'}
    p_neg = bool(p_t & neg)
    h_neg = bool(h_t & neg)
    if p_neg ^ h_neg:
        return {"label": "CONTRADICTION", "score": 0.9}

    label = 'ENTAILMENT' if score >= 0.6 else 'NEUTRAL'
    return {"label": label, "score": max(0.0, min(1.0, score))}
