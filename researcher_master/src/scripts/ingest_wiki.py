"""Simple script to ingest a list of Wikipedia pages into the FAISS retriever.

Usage:
    python -m src.scripts.ingest_wiki

It uses the `src.ingest.wikipedia.fetch_wikipedia_page` to fetch page text and then builds the FAISS index.
"""
from src.ingest.wikipedia import fetch_wikipedia_page
from src.rag.retriever import get_default_retriever
from src.ingest.ingest import ingest_text_chunks


def main():
    # small seed list; you can change or extend this
    seed_titles = [
        "History of science",
        "Philosophy of science",
        "Scientific method",
        "Epistemology",
        "History of mathematics",
        "Artificial intelligence",
        "Machine learning",
        "Mathematics",
    ]

    docs = []
    for title in seed_titles:
        print(f"Fetching: {title}")
        text = fetch_wikipedia_page(title)
        if not text:
            print(f"Failed to fetch: {title}")
            continue
        meta = {"source": "wikipedia", "title": title}
        chunk_docs = ingest_text_chunks(text, metadata=meta)
        docs.extend(chunk_docs)

    retriever = get_default_retriever()
    print(f"Building index from {len(docs)} chunks...")
    retriever.build_index(docs)
    retriever.save()
    print("Index built and saved to disk.")


if __name__ == '__main__':
    main()
