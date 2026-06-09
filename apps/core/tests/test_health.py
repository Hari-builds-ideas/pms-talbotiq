def test_healthz_returns_ok(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "service": "pms"}


def test_healthz_needs_no_auth(client):
    # No Authorization header at all — liveness must not be gated by auth.
    resp = client.get("/healthz")
    assert resp.status_code == 200
