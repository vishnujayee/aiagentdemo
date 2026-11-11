"""Simple ingestion helpers and chunker (stubs).

Extend these to support PDF/HTML parsing, metadata extraction, OCR, and embedding.
"""
from typing import List, Tuple
import re


def chunk_text(text: str, min_chunk_chars: int = 400, max_chunk_chars: int = 2000) -> List[str]:
    """Split text into paragraph-like chunks.

    Strategy:
    - Split by blank lines / paragraph markers
    - Merge short paragraphs to reach min_chunk_chars
    - Split very long paragraphs into slices of max_chunk_chars
    Returns a list of chunk strings.
    """
    if not text:
        return []

    # Normalize newlines
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: List[str] = []
    buffer = ""
    for p in paras:
        if len(p) >= max_chunk_chars:
            # split the long paragraph into pieces
            start = 0
            while start < len(p):
                end = min(len(p), start + max_chunk_chars)
                chunks.append(p[start:end])
                start = end
            continue

        if len(buffer) + len(p) + 1 <= min_chunk_chars:
            buffer = (buffer + "\n\n" + p).strip() if buffer else p
            continue

        if buffer:
            chunks.append(buffer)
        else:
            chunks.append(p)
        buffer = ""

    if buffer:
        chunks.append(buffer)

    return chunks


def ingest_text_chunks(text: str, metadata: dict = None) -> List[Tuple[str, str, dict]]:
    """Create chunk-level documents ready for indexing.

    Returns a list of tuples: (chunk_id, chunk_text, metadata_for_chunk)
    chunk_id is a short identifier generated from metadata (if present) plus an index.
    """
    chunks = chunk_text(text)
    docs = []
    base = metadata.get("title") if metadata and metadata.get("title") else "doc"
    for i, c in enumerate(chunks):
        cid = f"{base}__chunk_{i}"
        meta = metadata.copy() if metadata else {}
        meta.update({"chunk_index": i})
        docs.append((cid, c, meta))
    return docs
