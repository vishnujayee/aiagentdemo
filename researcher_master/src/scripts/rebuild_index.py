"""Script to rebuild the retriever index from stored chunks in the DB.

This reads chunks from `src.storage.db.get_chunks()` and rebuilds the default retriever,
persisting the index (or fallback metadata) so searches reflect newly ingested data.
"""
from src.storage.db import get_chunks
from src.rag.retriever import get_default_retriever


def main():
    chunks = get_chunks(limit=10000)
    docs = []
    for c in chunks:
        docs.append((c['id'], c['text'], c.get('meta', {})))

    retriever = get_default_retriever()
    retriever.build_index(docs)
    try:
        retriever.save()
    except Exception:
        # fallback retriever persists to .fallback.json automatically
        pass

    print(f"Rebuilt index with {len(docs)} docs")


if __name__ == '__main__':
    main()
