"""RAG module: retrieves relevant passages using the local retriever and
generates an answer via OpenAI (if API key provided), local LLM (Ollama/transformers), or lexical fallback.
"""
import os
from typing import List

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

from src.rag.retriever import get_default_retriever, REVIEW_QUEUE_PATH

try:
    import openai
except Exception:
    openai = None


def _build_prompt(question: str, contexts: List[dict]) -> str:
    prompt = "You are an expert researcher. Use the provided context snippets to answer the question."
    prompt += "\n\nContext snippets:\n"
    for i, c in enumerate(contexts, 1):
        meta = c.get("meta", {})
        title = meta.get("meta", {}).get("title") if meta else None
        source = meta.get("meta", {}).get("source") if meta else None
        text = meta.get("text") if meta else c.get("text")
        header = f"[{i}] source={source} title={title}\n"
        prompt += header
        # include a limited amount of each snippet
        snippet = (text or "")[:2000]
        prompt += snippet + "\n\n"
    prompt += "Question: " + question + "\n\nAnswer concisely and cite snippet numbers when appropriate."
    return prompt


def _answer_with_local_llm(prompt: str, contexts: List[dict], question: str, openai_error: Exception = None) -> str:
    """Use default LLM (Ollama / transformers / lexical) to generate answer from prompt."""
    try:
        from src.llm.llm import get_default_llm
        llm = get_default_llm()
        out = llm.generate(prompt, max_tokens=800)
        text = out.get("text") if isinstance(out, dict) else str(out)
        if text and text.strip():
            return text.strip()
    except Exception as e:
        pass
    # Fallback: return top context snippets
    combined = "\n\n".join([(c.get("meta", {}).get("text") or c.get("text") or "")[:1500] for c in contexts])
    err_note = f" (OpenAI failed: {openai_error})" if openai_error else ""
    return "(Local LLM used; no extra context below if index empty.)" + err_note + "\n\nTop snippets:\n\n" + (combined[:3000] or "No relevant passages in index. Run bootstrap_index or ingest_wiki to add content.")


def answer_question(question: str, top_k: int = 5) -> dict:
    retriever = get_default_retriever()
    hits = retriever.search(question, top_k=top_k)

    # Prepare simple context list (hits may have meta.text or meta with nested meta)
    contexts = []
    for h in hits:
        meta = h.get("meta") or {}
        text = meta.get("text") or (meta.get("meta", {}).get("text") if isinstance(meta.get("meta"), dict) else None)
        contexts.append({"meta": {**meta, "text": text or ""}, "text": text or ""})

    # Build prompt
    prompt = _build_prompt(question, contexts)

    # 1) OpenAI if key present
    if OPENAI_API_KEY and openai is not None:
        openai.api_key = OPENAI_API_KEY
        try:
            resp = openai.ChatCompletion.create(
                model=os.getenv("OPENAI_MODEL", "gpt-3.5-turbo"),
                messages=[{"role": "user", "content": prompt}],
                max_tokens=800,
                temperature=0.0,
            )
            ans = resp["choices"][0]["message"]["content"]
        except Exception as e:
            ans = _answer_with_local_llm(prompt, contexts, question, e)
    else:
        # 2) Local LLM (Ollama / transformers / lexical)
        ans = _answer_with_local_llm(prompt, contexts, question, None)

    # Format sources from hits (which have score and meta)
    sources = []
    top_score = None
    for i, h in enumerate(hits, 1):
        meta = h.get("meta") or {}
        score = h.get("score")
        if top_score is None or (score is not None and score > top_score):
            top_score = score
        text = meta.get("text") or (meta.get("meta", {}).get("text") if isinstance(meta.get("meta"), dict) else None)
        meta_obj = meta.get("meta") if isinstance(meta.get("meta"), dict) else meta
        sources.append({
            "rank": i,
            "score": score,
            "doc_id": meta.get("doc_id"),
            "meta": meta_obj,
            "source": meta_obj.get("source") if isinstance(meta_obj, dict) else None,
            "title": meta_obj.get("title") if isinstance(meta_obj, dict) else None,
            "url": meta_obj.get("url") if isinstance(meta_obj, dict) else None,
            "text": text,
        })

    # Persist retrieved sources into lightweight DB (best-effort)
    try:
        from src.storage import db as storage_db
        for s in sources:
            try:
                doc_id = s.get('doc_id') or f"src:retrieved:{hash(s.get('text') or '')}"
                # use doc_id as chunk id as well for simplicity
                storage_db.insert_chunk(doc_id, doc_id, s.get('text') or '', s.get('meta') or {})
            except Exception:
                # best-effort: don't fail RAG if DB insert fails
                pass
    except Exception:
        pass

    result = {"answer": ans, "sources": sources}

    # If top_score is very low or no sources, add to review queue for human verification
    try:
        if top_score is None or float(top_score) < 0.05:
            # append to review queue
            import json
            import time

            q_entry = {"question": question, "timestamp": time.time(), "sources": sources}
            os.makedirs(os.path.dirname(REVIEW_QUEUE_PATH), exist_ok=True)
            if os.path.exists(REVIEW_QUEUE_PATH):
                with open(REVIEW_QUEUE_PATH, "r", encoding="utf-8") as f:
                    queue = json.load(f)
            else:
                queue = []
            queue.append(q_entry)
            with open(REVIEW_QUEUE_PATH, "w", encoding="utf-8") as f:
                json.dump(queue, f, indent=2)
    except Exception:
        # non-fatal: review queue best-effort
        pass

    return result
