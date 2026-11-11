"""Synthesis and learning planner utilities.

This module provides a simple heuristic-based mastery report generator for the
prototype. It inspects provided KG and mapping to produce a learning roadmap,
gaps, recommended readings and exercises.
"""
from typing import Dict, Any, List


def generate_mastery_report(topic: str, kg: Dict[str, Any], mapping: Dict[str, Any]) -> Dict[str, Any]:
    """Produce a lightweight mastery report for a topic.

    This is a prototype implementation that ranks KG nodes by degree and
    suggests readings from mapping entries.
    """
    nodes = kg.get("nodes", []) if kg else []
    edges = kg.get("edges", []) if kg else []

    # top nodes by count or fallback to first nodes
    ranked = sorted(nodes, key=lambda n: n.get("count", 1), reverse=True)[:10]

    learning_plan: List[Dict[str, Any]] = []
    for n in ranked:
        label = n.get("label")
        mapped = mapping.get(label, {}).get("mapping", []) if mapping else []
        readings = [ {"doc_id": m.get("doc_id"), "score": m.get("score"), "text_preview": (m.get("text") or "")[:400]} for m in mapped[:3] ]
        learning_plan.append({"node": label, "reason": "high connectivity or frequency", "readings": readings})

    gaps = []
    # simple gap heuristic: nodes with low mapping coverage
    for n in nodes:
        label = n.get("label")
        mapped = mapping.get(label, {}).get("mapping", []) if mapping else []
        if len(mapped) == 0:
            gaps.append({"node": label, "issue": "no source passages mapped"})

    report = {
        "topic": topic,
        "summary": f"Mastery report for {topic}: {len(nodes)} KG nodes, {len(edges)} edges.",
        "learning_plan": learning_plan,
        "gaps": gaps,
        "recommendation": "Follow the ordered learning_plan and review gap nodes by sourcing more documents."
    }
    return report
