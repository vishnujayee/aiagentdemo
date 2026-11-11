import sys
import types


def test_verifier_agent_basic(monkeypatch):
    # Prepare dummy modules to avoid importing heavy dependencies
    dummy_rag = types.SimpleNamespace()

    class DummyRetriever:
        def search(self, text, top_k=5):
            return [{
                'id': 'e1',
                'meta': {'text': 'Water boils at 100°C at sea level.', 'doc_id': 'doc1'},
                'score': 0.9
            }]

    dummy_rag.get_default_retriever = lambda: DummyRetriever()
    sys.modules['src.rag.retriever'] = dummy_rag

    # Dummy storage.db with enqueue_review no-op
    dummy_db = types.SimpleNamespace()
    dummy_db.enqueue_review = lambda x: None
    sys.modules['src.storage.db'] = dummy_db

    # Now import the verifier agent (it will use our mocked modules)
    import importlib
    vmod = importlib.import_module('src.verifier.agent')

    res = vmod.verifier_agent([{'text': 'Water boils at 100 degrees Celsius.'}])
    assert isinstance(res, list)
    assert res and 'confidence' in res[0]
