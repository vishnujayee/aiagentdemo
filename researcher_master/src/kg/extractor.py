"""Simple Knowledge Graph extractor.

This module uses spaCy to extract named entities and noun-chunk co-occurrences
from chunked documents and produces a lightweight graph structure (nodes + edges).

It is intentionally simple and meant to be replaced by a more robust IE pipeline
for production (OpenIE, relation extraction models, or supervised extractors).
"""
from typing import Dict, List, Tuple
import os
import json
import re

try:
    import spacy
except Exception:
    spacy = None


def _ensure_spacy():
    if spacy is None:
        raise RuntimeError("spaCy not installed. Install with 'pip install spacy' and download 'en_core_web_sm'.")


def _canonicalize_text(s: str) -> str:
    """Very small canonicalization: lowercase, remove punctuation, collapse spaces."""
    t = s or ""
    t = t.strip().lower()
    # remove punctuation except internal hyphens
    t = re.sub(r"[^\w\s-]", "", t)
    t = re.sub(r"\s+", " ", t)
    return t


def extract_entities_and_relations(chunks: List[Dict]) -> Dict:
    """Given a list of chunks (each dict must contain 'doc_id' and 'text' and 'meta'),
    return a graph dict with nodes and edges.

    nodes: dict mapping canonical entity -> {id, label, type, count}
    edges: list of {source, target, relation, count}
    """
    # If spaCy is available, use it for richer entity types and lemmatization.
    use_spacy = spacy is not None
    if use_spacy:
        nlp = spacy.load("en_core_web_sm")

    nodes: Dict[str, Dict] = {}
    edges: Dict[Tuple[str, str, str], int] = {}

    def add_node(ent_text: str, ent_label: str):
        if not ent_text:
            return
        # canonicalize to collapse variants like 'NASA' and 'Nasa'
        key = _canonicalize_text(ent_text)
        if key == "":
            return
        node = nodes.get(key)
        # label is the original most-frequent surface form; prefer the longer/original
        label = ent_text.strip()
        if node is None:
            nodes[key] = {"id": key, "label": label, "type": ent_label, "count": 1}
        else:
            node["count"] += 1
            # prefer existing label unless new label is longer (heuristic)
            if len(label) > len(node.get("label", "")):
                node["label"] = label

    def add_edge(a: str, b: str, relation: str = "cooccurs"):
        if a == b:
            return
        key = (a, b, relation)
        edges[key] = edges.get(key, 0) + 1

    for chunk in chunks:
        text = chunk.get("text") or chunk.get("meta", {}).get("text")
        if not text:
            continue
        if use_spacy:
            doc = nlp(text)
            # collect entity texts in this chunk
            ents = [ent.text.strip() for ent in doc.ents if ent.text.strip()]
            # also include frequent noun-chunks as candidate concepts
            noun_chunks = [nc.text.strip() for nc in doc.noun_chunks if nc.text.strip()]
            concepts = list(dict.fromkeys(ents + noun_chunks))  # preserve order, dedupe

            # add nodes
            for ent in concepts:
                label = "CONCEPT"
                for e in doc.ents:
                    if e.text.strip() == ent:
                        label = e.label_
                        break
                add_node(ent, label)
        else:
            # Lightweight fallback: title-case phrases and frequent tokens.
            concepts = []
            title_phrases = re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3}\b", text)
            concepts.extend([p.strip() for p in title_phrases if p.strip()])
            toks = re.findall(r"\b[a-zA-Z]{4,}\b", text.lower())
            if toks:
                freq = {}
                for t in toks:
                    freq[t] = freq.get(t, 0) + 1
                common = sorted(freq.items(), key=lambda kv: kv[1], reverse=True)[:12]
                concepts.extend([w for w, _ in common])
            concepts = list(dict.fromkeys([c for c in concepts if c]))
            for ent in concepts:
                add_node(ent, "CONCEPT")

        # add co-occurrence edges among concepts
        for i in range(len(concepts)):
            for j in range(i + 1, len(concepts)):
                a = concepts[i]
                b = concepts[j]
                add_edge(a, b, relation="cooccurs_in_chunk")

    # format edges list
    edges_list = []
    for (a, b, rel), count in edges.items():
        edges_list.append({"source": a, "target": b, "relation": rel, "count": count})

    graph = {"nodes": list(nodes.values()), "edges": edges_list}
    return graph


def save_graph(graph: Dict, path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(graph, f, indent=2)
