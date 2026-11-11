"""Developer script: run a minimal end-to-end flow locally without heavy deps.

It will:
- initialize the DB
- register the improved verifier if available
- ingest a small sample document
- run a sample query against the retriever
- run the verifier on a sample claim
"""
from src.logging_config import configure_logging
configure_logging()

import os
import importlib
from src.storage.db import init_db
from src.rag.retriever import get_default_retriever
from src.ingest.ingest import ingest_text_chunks


def _resolve_orchestrator():
    """Resolve orchestrator robustly even if tests monkeypatch sys.modules."""
    try:
        from src.orchestrator import orchestrator as orch
        return orch
    except Exception:
        pass
    try:
        mod = importlib.import_module("src.orchestrator.orchestrator")
        orch_cls = getattr(mod, "Orchestrator", None)
        if orch_cls is None:
            return None
        orch = orch_cls()
        for name in ("discovery_agent", "ingest_agent", "verifier_agent"):
            fn = getattr(mod, name, None)
            if fn is not None:
                orch.register_agent(name.replace("_agent", ""), fn)
        return orch
    except Exception:
        return None


def main():
    print("Initializing DB...")
    init_db()
    orchestrator = _resolve_orchestrator()

    # try to register improved verifier with orchestrator if available
    try:
        if orchestrator is None:
            raise RuntimeError("orchestrator unavailable")
        from src.verifier.agent import verifier_agent as improved_verifier
        orchestrator.register_agent('verifier', improved_verifier)
        print("Registered improved verifier in orchestrator")
    except Exception:
        print("Improved verifier not available; using default")

    # sample document
    doc = {
        'id': 'sample1',
        'text': 'Water boils at 100 degrees Celsius at sea level. Photosynthesis converts sunlight into chemical energy.',
        'meta': {'source': 'local', 'title': 'Sample Doc'}
    }

    print("Ingesting sample document...")
    if orchestrator is not None:
        orchestrator.run_agent('ingest', [doc])
    else:
        ingest_text_chunks(doc["text"], metadata=doc["meta"])

    retriever = get_default_retriever()
    print("Running sample search for 'water boils'...")
    res = retriever.search('water boils', top_k=3)
    print('Search results:', res)

    # run verifier on a simple claim
    print('Running verifier on a claim...')
    claim_item = {'text': 'Water boils at 100 degrees Celsius.'}
    if orchestrator is not None:
        verdicts = orchestrator.run_agent('verifier', [claim_item])
    else:
        verdicts = []
    print('Verifier results:', verdicts)


if __name__ == '__main__':
    main()
