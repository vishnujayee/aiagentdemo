"""FAISS-backed retriever using sentence-transformers.

Simple implementation that supports:
- creating an index from a list of (doc_id, text, metadata)
- saving/loading index and metadata
- searching top_k similar passages

This is intentionally simple and easy to extend (add BM25, hybrid, Weaviate, Pinecone, etc.).
"""
import os
import pickle
from typing import List, Dict, Tuple

try:
    import faiss
    import numpy as np
except Exception:
    faiss = None
    np = None

import re
try:
    from sentence_transformers import SentenceTransformer
    _HAS_SENTENCE_TRANSFORMERS = True
except Exception:
    SentenceTransformer = None
    _HAS_SENTENCE_TRANSFORMERS = False
from rank_bm25 import BM25Okapi

VECTOR_DB_PATH = os.getenv("VECTOR_DB_PATH", "./data/faiss.index")
METADATA_PATH = os.getenv("METADATA_PATH", "./data/metadata.pkl")
EMBED_MODEL_NAME = os.getenv("EMBED_MODEL_NAME", "all-MiniLM-L6-v2")
REVIEW_QUEUE_PATH = os.getenv("REVIEW_QUEUE_PATH", "./data/review_queue.json")

# Ensure data dir exists
os.makedirs(os.path.dirname(VECTOR_DB_PATH), exist_ok=True)


class Retriever:
    def __init__(self, embed_model_name: str = EMBED_MODEL_NAME):
        if not _HAS_SENTENCE_TRANSFORMERS:
            raise RuntimeError("sentence-transformers not available")
        self.model = SentenceTransformer(embed_model_name)
        self.index = None
        self.id_to_meta: Dict[int, Dict] = {}
        self.bm25 = None
        self.corpus_tokenized: List[List[str]] = []
        # simple in-memory cache for recent queries to avoid repeated heavy ops
        self._search_cache = {}

    def _ensure_index(self, dim: int):
        if self.index is None:
            if faiss is None:
                raise RuntimeError("faiss is not available. Install faiss-cpu or faiss-gpu.")
            self.index = faiss.IndexFlatIP(dim)  # inner product on normalized vectors

    def build_index(self, docs: List[Tuple[str, str, Dict]]):
        """Build index from docs: list of (doc_id, text, metadata)
        doc_id: unique string id
        text: content to embed
        metadata: dict with source, title, etc.
        Also builds a BM25 index over tokenized chunks for a hybrid search.
        """
        texts = [t for (_id, t, _m) in docs]
        embs = self.model.encode(texts, convert_to_numpy=True, show_progress_bar=True)
        # normalize for IP
        try:
            faiss.normalize_L2(embs)
        except Exception:
            if np is None:
                raise
            # embs = embs / np.linalg.norm(embs, axis=1, keepdims=True)
            embs = np.array(embs)
            if embs.ndim == 1:
                embs = embs.reshape(1, -1)
            norms = np.linalg.norm(embs, axis=1, keepdims=True)
            norms[norms == 0] = 1  # avoid division by zero
            embs = embs / norms
            embs = np.array(embs)
        dim = embs.shape[1]
        self._ensure_index(dim)
        self.index.add(embs)
        # store metadata mapping by integer id
        start = len(self.id_to_meta)
        for i, (_id, _t, meta) in enumerate(docs):
            self.id_to_meta[start + i] = {"doc_id": _id, "meta": meta, "text": _t}

        # build BM25
        # lightweight tokenizer to avoid heavy NLTK dependency
        def _tokenize(s: str):
            return re.findall(r"\w+", s.lower())

        self.corpus_tokenized = [_tokenize(t) for t in texts]
        if self.corpus_tokenized:
            self.bm25 = BM25Okapi(self.corpus_tokenized)

    def save(self, index_path: str = VECTOR_DB_PATH, meta_path: str = METADATA_PATH):
        if self.index is None:
            raise RuntimeError("Index is empty")
        faiss.write_index(self.index, index_path)
        with open(meta_path, "wb") as f:
            pickle.dump({"id_to_meta": self.id_to_meta, "corpus_tokenized": self.corpus_tokenized}, f)

    def load(self, index_path: str = VECTOR_DB_PATH, meta_path: str = METADATA_PATH):
        if not os.path.exists(index_path) or not os.path.exists(meta_path):
            raise FileNotFoundError("Index or metadata not found")
        self.index = faiss.read_index(index_path)
        with open(meta_path, "rb") as f:
            data = pickle.load(f)
            self.id_to_meta = data.get("id_to_meta", {})
            self.corpus_tokenized = data.get("corpus_tokenized", [])
        if self.corpus_tokenized:
            self.bm25 = BM25Okapi(self.corpus_tokenized)

    def search(self, query: str, top_k: int = 5, alpha: float = 0.6) -> List[Dict]:
        """Hybrid search: combine vector similarity and BM25 scores.

        alpha controls weight of vector score vs BM25 (0..1). Returns list of dicts with score and meta.
        """
        if self.index is None:
            # try to load
            try:
                self.load()
            except Exception:
                return []

        # Simple in-process cache (keyed by query, top_k, alpha)
        cache_key = (query, int(top_k), float(alpha))
        if cache_key in self._search_cache:
            return self._search_cache[cache_key]

        # Vector search
        q_emb = self.model.encode([query], convert_to_numpy=True)
        try:
            faiss.normalize_L2(q_emb)
        except Exception:
            q_emb = q_emb / np.linalg.norm(q_emb, axis=1, keepdims=True)
        D, I = self.index.search(q_emb, top_k)
        vec_results = []
        for score, idx in zip(D[0], I[0]):
            if idx < 0:
                continue
            meta = self.id_to_meta.get(int(idx), {})
            # faiss inner-product on normalized vectors approximates cosine in [-1,1]
            # remap to [0,1] for easier combination with BM25
            try:
                vec_score = float((score + 1.0) / 2.0)
            except Exception:
                vec_score = float(score)
            vec_results.append({"idx": int(idx), "vec_score": vec_score, "meta": meta})

        # BM25 search
        bm25_results = []
        if self.bm25 is not None:
            def _tokenize(s: str):
                return re.findall(r"\w+", s.lower())

            q_tokens = _tokenize(query)
            scores = self.bm25.get_scores(q_tokens)
            top_idxs = list(sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k])
            for idx in top_idxs:
                bm25_results.append({"idx": int(idx), "bm25_score": float(scores[idx])})

        # merge results by idx
        merged = {}
        for r in vec_results:
            idx = r["idx"]
            merged[idx] = {"vec_score": r.get("vec_score", 0.0), "meta": r.get("meta")}
        for r in bm25_results:
            idx = r["idx"]
            if idx not in merged:
                meta = self.id_to_meta.get(int(idx), {})
                merged[idx] = {"vec_score": 0.0, "meta": meta}
            merged[idx]["bm25_score"] = r.get("bm25_score", 0.0)

        # compute combined scores
        results = []
        # normalize bm25 scores to 0..1 by dividing by observed max
        bm_vals = [v.get("bm25_score", 0.0) for v in merged.values()]
        bm_max = max(bm_vals) if bm_vals else 0.0
        for idx, v in merged.items():
            vec_s = v.get("vec_score", 0.0)
            bm_s = v.get("bm25_score", 0.0)
            norm_bm = (bm_s / bm_max) if bm_max and bm_s else (0.0 if bm_max else 0.0)
            # combined score in 0..1
            combined = alpha * vec_s + (1 - alpha) * norm_bm
            results.append({"score": float(combined), "meta": v.get("meta"), "idx": int(idx)})

        # sort and return top_k
        results = sorted(results, key=lambda r: r["score"], reverse=True)[:top_k]
        # cache result (small cache; keys are short strings)
        try:
            self._search_cache[cache_key] = results
            # keep cache size bounded
            if len(self._search_cache) > 256:
                # drop oldest entry arbitrarily
                self._search_cache.pop(next(iter(self._search_cache)))
        except Exception:
            pass
        return results

    def clear_cache(self):
        try:
            self._search_cache.clear()
        except Exception:
            self._search_cache = {}


# convenience single instance functions
_default_retriever: Retriever = None


def get_default_retriever() -> Retriever:
    global _default_retriever
    if _default_retriever is None:
        # Allow explicit backend selection via env var. Defaults to 'auto'.
        backend = os.getenv('VECTOR_BACKEND', 'auto').lower()
        use_full = False
        # Keep defaults lightweight/local-first.
        # Full vector backend is opt-in via VECTOR_BACKEND=faiss|full.
        if backend in ('faiss', 'full'):
            use_full = True
        elif backend in ('bm25', 'fallback'):
            use_full = False
        elif backend == 'auto':
            use_full = False
        else:
            use_full = False

        # prefer full Retriever when sentence-transformers is available (or requested), else use lightweight fallback
        if use_full and _HAS_SENTENCE_TRANSFORMERS and faiss is not None:
            _default_retriever = Retriever()
        else:
            # lightweight BM25-only retriever fallback
            class FallbackRetriever:
                def __init__(self):
                    self.docs = []  # list of (doc_id, text, meta)
                    self.bm25 = None
                    self.corpus_tokenized = []
                    self._search_cache = {}

                def build_index(self, docs: List[Tuple[str, str, Dict]]):
                    self.docs = docs.copy()
                    def _tokenize(s: str):
                        return re.findall(r"\w+", s.lower())
                    texts = [t for (_id, t, _m) in docs]
                    self.corpus_tokenized = [_tokenize(t) for t in texts]
                    if self.corpus_tokenized:
                        self.bm25 = BM25Okapi(self.corpus_tokenized)

                def save(self, *args, **kwargs):
                    # persist fallback docs and tokenization to a JSON metadata file
                    import json
                    path = kwargs.get('meta_path') or METADATA_PATH + '.fallback.json'
                    data = {
                        'docs': self.docs,
                        'corpus_tokenized': self.corpus_tokenized,
                    }
                    with open(path, 'w', encoding='utf-8') as f:
                        json.dump(data, f)
                    return

                def load(self, *args, **kwargs):
                    # try to load fallback metadata
                    import json
                    path = kwargs.get('meta_path') or METADATA_PATH + '.fallback.json'
                    if not os.path.exists(path):
                        return
                    with open(path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    self.docs = data.get('docs', [])
                    self.corpus_tokenized = data.get('corpus_tokenized', [])
                    if self.corpus_tokenized:
                        self.bm25 = BM25Okapi(self.corpus_tokenized)
                    return

                def search(self, query: str, top_k: int = 5, alpha: float = 0.6):
                    # cache key and simple in-memory caching
                    cache_key = (query, int(top_k), float(alpha))
                    if cache_key in self._search_cache:
                        return self._search_cache[cache_key]

                    if not self.bm25:
                        return []
                    def _tokenize(s: str):
                        return re.findall(r"\w+", s.lower())
                    q_tokens = _tokenize(query)
                    scores = self.bm25.get_scores(q_tokens)
                    top_idxs = list(sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k])
                    results = []
                    for idx in top_idxs:
                        _id, _text, meta = self.docs[idx]
                        results.append({"score": float(scores[idx]), "meta": {"doc_id": _id, "meta": meta, "text": _text}, "idx": int(idx)})
                    # normalize BM25 scores to 0..1 using observed max
                    vals = [r["score"] for r in results]
                    maxv = max(vals) if vals else 0.0
                    if maxv > 0:
                        for r in results:
                            r["score"] = float(r["score"] / maxv)
                    try:
                        self._search_cache[cache_key] = results
                        if len(self._search_cache) > 256:
                            self._search_cache.pop(next(iter(self._search_cache)))
                    except Exception:
                        pass
                    return results

                def clear_cache(self):
                    try:
                        self._search_cache.clear()
                    except Exception:
                        self._search_cache = {}

            _default_retriever = FallbackRetriever()
    # Try to load persisted fallback metadata if present to make the retriever ready on first use
    try:
        # call load on the instance (both full Retriever and FallbackRetriever implement load)
        _default_retriever.load()
    except Exception:
        # non-fatal; it's okay if no saved index exists yet
        pass

    return _default_retriever
    
