"""Map KG nodes to indexed chunks via the retriever.

For each node in the KG (by label), find top-k matching chunks from the vector+BM25 retriever.
Saves mapping to `./data/kg_mapping.json` and returns the mapping dict.
"""
import os
import json
from typing import Dict, Any

from src.rag.retriever import get_default_retriever


def map_kg_to_chunks(kg_path: str = "./data/kg.json", out_path: str = "./data/kg_mapping.json", top_k: int = 3) -> Dict[str, Any]:
    if not os.path.exists(kg_path):
        raise FileNotFoundError(f"KG not found at {kg_path}; build it first with build_kg.py")

    with open(kg_path, "r", encoding="utf-8") as f:
        kg = json.load(f)

    nodes = kg.get("nodes", [])
    retriever = get_default_retriever()

    mapping = {}
    for node in nodes:
        label = node.get("label")
        if not label:
            continue
        hits = retriever.search(label, top_k=top_k)
        # keep doc_id, score, snippet text
        mapped = []
        for h in hits:
            meta = h.get("meta", {})
            mapped.append({
                "doc_id": meta.get("doc_id"),
                "score": h.get("score"),
                "meta": meta.get("meta"),
                "text": meta.get("text"),
            })
        mapping[label] = {"node": node, "mapping": mapped}

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(mapping, f, indent=2)

    return mapping


if __name__ == '__main__':
    print("Mapping KG to chunks...")
    m = map_kg_to_chunks()
    print(f"Wrote mapping with {len(m)} nodes")
