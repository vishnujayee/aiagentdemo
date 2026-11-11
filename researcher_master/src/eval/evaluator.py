"""Evaluation utilities for answers and KG coverage.

Provides simple, local-only heuristics for prototype evaluation.
"""
from typing import Dict, Any, List


def evaluate_answer(answer: str, references: List[str]) -> Dict[str, Any]:
    """Return quick evaluation metrics for an answer given references.

    This is a naive implementation: checks presence of reference strings
    and returns simple precision-like scores.
    """
    lower = answer.lower()
    matches = 0
    for r in references:
        if r.lower() in lower:
            matches += 1
    coverage = matches / max(1, len(references))
    return {"matches": matches, "reference_count": len(references), "coverage": coverage}


def evaluate_kg_coverage(kg: Dict[str, Any]) -> Dict[str, Any]:
    nodes = kg.get("nodes", []) if kg else []
    edges = kg.get("edges", []) if kg else []
    avg_degree = 0.0
    try:
        if nodes:
            avg_degree = sum([n.get("count", 1) for n in nodes]) / len(nodes)
    except Exception:
        avg_degree = 0.0
    return {"node_count": len(nodes), "edge_count": len(edges), "avg_degree": avg_degree}
