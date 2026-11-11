"""Utilities for working with the KG produced by extractor.

Currently provides a simple function to load and query the graph JSON.
"""
import json
from typing import Dict, List


def load_graph(path: str) -> Dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def top_nodes(graph: Dict, top_n: int = 20) -> List[Dict]:
    nodes = graph.get("nodes", [])
    nodes_sorted = sorted(nodes, key=lambda n: n.get("count", 0), reverse=True)
    return nodes_sorted[:top_n]
