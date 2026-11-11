"""Basic evaluation harness for answers and KG coverage.

This module provides simple, local-first evaluation metrics that can be
extended later. For now it offers:
- evaluate_answer(answer, references): returns precision-like score based on
  token overlap with references (very simple)
- evaluate_kg_coverage(kg): returns number of nodes and edges as a basic metric
"""
from typing import List, Dict
import re


def _tokens(text: str):
    return set(re.findall(r"\w{3,}", text.lower()))


def evaluate_answer(answer: str, references: List[str]) -> Dict:
    ans_tokens = _tokens(answer)
    ref_tokens = set().union(*[ _tokens(r) for r in references ]) if references else set()
    if not ans_tokens:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0}
    tp = len(ans_tokens & ref_tokens)
    precision = tp / len(ans_tokens)
    recall = tp / len(ref_tokens) if ref_tokens else 0.0
    if precision + recall == 0:
        f1 = 0.0
    else:
        f1 = 2 * (precision * recall) / (precision + recall)
    return {"precision": precision, "recall": recall, "f1": f1}


def evaluate_kg_coverage(kg: Dict) -> Dict:
    nodes = kg.get('nodes') if isinstance(kg, dict) else None
    edges = kg.get('edges') if isinstance(kg, dict) else None
    return {"nodes": len(nodes) if nodes else 0, "edges": len(edges) if edges else 0}


if __name__ == '__main__':
    print(evaluate_answer('Water boils at 100 degrees Celsius', ['Water boils at 100°C at sea level.']))
