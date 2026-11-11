import importlib
import sys
import types


def test_run_cycle_basic(monkeypatch):
    # Mock orchestrator with discovery, verifier, ingest agents
    orchestrator = types.SimpleNamespace()

    # discovery: push one candidate into storage discovery queue
    def discovery_agent(seeds):
        # simulate writing to DB by creating get_discovery_queue to return one item
        return [{"id": "c1", "item": {"id": "c1", "text": "Water boils at 100 degrees C.", "url": "https://example.org/doc1"}}]

    orchestrator.run_agent = lambda name, *args, **kwargs: discovery_agent(args[0]) if name == 'discovery' else []

    # Mock DB storage functions
    dummy_db = types.SimpleNamespace()
    # discovery queue contains one candidate
    dummy_db._queue = [{"id": "c1", "item": {"id": "c1", "text": "Water boils at 100 degrees C.", "url": "https://example.org/doc1"}}]

    def get_discovery_queue():
        return list(dummy_db._queue)

    def remove_discovery_candidate(cid):
        dummy_db._queue = [q for q in dummy_db._queue if q.get('id') != cid]

    def enqueue_review(x):
        dummy_db.review = x

    dummy_db.get_discovery_queue = get_discovery_queue
    dummy_db.remove_discovery_candidate = remove_discovery_candidate
    dummy_db.enqueue_review = enqueue_review

    sys.modules['src.storage.db'] = dummy_db

    # Mock orchestrator module
    sys.modules['src.orchestrator'] = orchestrator

    # Mock safety policy to allow urls
    sys.modules['src.safety.policy'] = types.SimpleNamespace(is_allowed_url=lambda u: True)

    # Import and run the manager
    mgr = importlib.import_module('src.continuous.manager')
    res = mgr.run_cycle(seeds=['test'])
    assert isinstance(res, dict)
    assert 'queue_snapshot' in res
