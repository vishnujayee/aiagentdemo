import time
from fastapi.testclient import TestClient

from src.app.main import app


client = TestClient(app)


def test_admin_endpoints_start_stop():
    # Start orchestrator
    r = client.post('/admin/orchestrator/start')
    assert r.status_code == 200

    # Start worker
    r = client.post('/admin/worker/start', json={'name': 'discovery_worker', 'interval': 1})
    assert r.status_code == 200

    # seed a discovery (uses wikipedia fallback)
    r = client.post('/admin/discover', json={'seeds': ['Water boiling']})
    assert r.status_code == 200
    data = r.json()
    assert 'queue_count' in data or 'found' in data

    # start autonomy for a very short loop and then stop
    r = client.post('/admin/autonomy/start', json={'goal': 'Collect evidence for water boiling', 'interval': 2})
    assert r.status_code == 200
    time.sleep(3)
    r = client.get('/admin/autonomy/status')
    assert r.status_code == 200
    status = r.json()
    assert 'running' in status

    # stop autonomy and worker
    r = client.post('/admin/autonomy/stop')
    assert r.status_code == 200
    r = client.post('/admin/worker/stop', json={'name': 'discovery_worker'})
    assert r.status_code == 200
