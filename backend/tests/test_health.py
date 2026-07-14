"""Phase 0 acceptance test: the /health endpoint returns 200."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_200():
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "version" in body
    assert "time" in body


def test_ready_returns_200():
    resp = client.get("/health/ready")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"


def test_openapi_available():
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    assert resp.json()["info"]["title"]
