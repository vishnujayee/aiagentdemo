"""Bootstrap script to create a lightweight retriever index from bundled sample documents.

Usage: python -m src.scripts.bootstrap_index
This builds a BM25 fallback index (no faiss/sentence-transformers required) and saves metadata
so `/src/rag/retriever.py`'s fallback retriever can load it.
"""
import json
import os
from typing import List, Tuple, Dict

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
SAMPLE_PATH = os.path.join(PROJECT_ROOT, 'data', 'sample_docs.json')
METADATA_PATH = os.getenv('METADATA_PATH', os.path.join(PROJECT_ROOT, 'data', 'metadata.pkl'))


def load_samples() -> List[Tuple[str, str, Dict]]:
    if not os.path.exists(SAMPLE_PATH):
        # create a small set of example docs
        docs = [
            {
                "id": "doc:rl_intro",
                "title": "Reinforcement Learning - Intro",
                "text": "Reinforcement learning (RL) is an area of machine learning where agents learn to make decisions by trial and error, receiving rewards for desirable actions.",
                "meta": {"source": "sample", "title": "Reinforcement Learning - Intro"}
            },
            {
                "id": "doc:rag_overview",
                "title": "Retrieval-Augmented Generation",
                "text": "Retrieval-augmented generation (RAG) combines a retriever that fetches documents with a generator (like a language model) to produce answers grounded in the retrieved evidence.",
                "meta": {"source": "sample", "title": "RAG Overview"}
            },
            {
                "id": "doc:faiss_note",
                "title": "FAISS Note",
                "text": "FAISS is a library for efficient similarity search and clustering of dense vectors. For small local setups, a BM25 fallback is often sufficient.",
                "meta": {"source": "sample", "title": "FAISS Note"}
            }
        ]
        os.makedirs(os.path.dirname(SAMPLE_PATH), exist_ok=True)
        with open(SAMPLE_PATH, 'w', encoding='utf-8') as f:
            json.dump(docs, f, indent=2)
    else:
        with open(SAMPLE_PATH, 'r', encoding='utf-8') as f:
            docs = json.load(f)

    # convert to expected tuple format: (doc_id, text, metadata)
    out = []
    for d in docs:
        out.append((d.get('id'), d.get('text', ''), d.get('meta', {})))
    return out


def build_and_save():
    docs = load_samples()
    # Use retriever fallback builder
    from src.rag.retriever import get_default_retriever, METADATA_PATH as META_ENV

    retr = get_default_retriever()
    retr.build_index(docs)
    # save using retriever save; fallback saves to a JSON metadata path
    try:
        retr.save()
        print(f"Index built and saved (metadata path: {META_ENV})")
    except Exception as e:
        print(f"Warning: retriever.save() failed: {e}")


if __name__ == '__main__':
    build_and_save()
