"""Build a Knowledge Graph from the existing indexed chunks.

This script expects that `src/rag/retriever.py` has produced `./data/metadata.pkl`
containing the indexed chunks (id_to_meta mapping with 'text' and 'meta').

It will create `./data/kg.json`.
"""
import os
import pickle
from src.kg.extractor import extract_entities_and_relations, save_graph


def main():
    meta_path = os.getenv("METADATA_PATH", "./data/metadata.pkl")
    out_path = os.getenv("KG_OUT_PATH", "./data/kg.json")

    if not os.path.exists(meta_path):
        print(f"Metadata not found at {meta_path}. Run the ingest script first.")
        return

    with open(meta_path, "rb") as f:
        data = pickle.load(f)

    # Support multiple metadata formats used by retriever backends.
    items = []
    if isinstance(data, dict) and "id_to_meta" in data and isinstance(data["id_to_meta"], dict):
        items = list(data["id_to_meta"].values())
    elif isinstance(data, dict) and "docs" in data and isinstance(data["docs"], list):
        for d in data["docs"]:
            if isinstance(d, (list, tuple)) and len(d) >= 3:
                doc_id, text, meta = d[0], d[1], d[2]
                items.append({"doc_id": doc_id, "text": text, "meta": meta})
    elif isinstance(data, dict):
        vals = list(data.values())
        if vals and all(isinstance(v, dict) and ("text" in v or "meta" in v) for v in vals):
            items = vals
    print(f"Building KG from {len(items)} chunks...")
    graph = extract_entities_and_relations(items)
    save_graph(graph, out_path)
    print(f"KG saved to {out_path}")


if __name__ == '__main__':
    main()
