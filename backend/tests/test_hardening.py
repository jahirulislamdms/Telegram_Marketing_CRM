"""Phase 12 acceptance: hardening (rate limiting, security headers, readiness, secrets)."""

import pytest

from app import cli
from app.config import settings


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ------------------------------------------------------- security headers ----


def test_security_headers_present(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert r.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "Strict-Transport-Security" in r.headers


def test_security_headers_on_api_responses(client):
    # 401 (unauthenticated) responses still carry the headers.
    r = client.get("/api/accounts")
    assert r.status_code == 401
    assert r.headers["X-Content-Type-Options"] == "nosniff"


# --------------------------------------------------------- rate limiting -----


def test_rate_limit_disabled_by_default(client):
    # conftest disables rate limiting for the suite -> no 429 no matter how many.
    for _ in range(15):
        r = client.post("/api/auth/login", json={"email": "x@y.z", "password": "nope"})
        assert r.status_code != 429


def test_login_rate_limit_returns_429(client, monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_login_per_minute", 3)
    monkeypatch.setattr(settings, "rate_limit_window_seconds", 60)
    # Unique client IP so this test's window is isolated from any other.
    headers = {"X-Forwarded-For": "203.0.113.10"}
    body = {"email": "brute@test.com", "password": "wrong"}

    statuses = [client.post("/api/auth/login", json=body, headers=headers).status_code for _ in range(3)]
    assert all(s == 401 for s in statuses)  # first 3 allowed (bad creds -> 401)

    blocked = client.post("/api/auth/login", json=body, headers=headers)
    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers
    assert int(blocked.headers["Retry-After"]) >= 1
    assert blocked.headers["X-RateLimit-Remaining"] == "0"


def test_rate_limit_is_per_ip(client, monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_login_per_minute", 2)
    monkeypatch.setattr(settings, "rate_limit_window_seconds", 60)
    body = {"email": "a@test.com", "password": "wrong"}

    # Exhaust IP A.
    for _ in range(2):
        client.post("/api/auth/login", json=body, headers={"X-Forwarded-For": "198.51.100.1"})
    assert client.post("/api/auth/login", json=body, headers={"X-Forwarded-For": "198.51.100.1"}).status_code == 429
    # A different IP is unaffected.
    assert client.post("/api/auth/login", json=body, headers={"X-Forwarded-For": "198.51.100.2"}).status_code == 401


def test_rate_limit_headers_on_allowed_request(client, monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_per_minute", 100)
    r = client.get("/api/accounts", headers={"X-Forwarded-For": "203.0.113.55"})
    # Unauthenticated -> 401, but the limiter still annotates the response.
    assert "X-RateLimit-Limit" in r.headers
    assert r.headers["X-RateLimit-Limit"] == "100"


def test_health_not_rate_limited(client, monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_per_minute", 1)
    # /health is exempt (not under /api/*): many calls, never 429.
    for _ in range(5):
        assert client.get("/health", headers={"X-Forwarded-For": "203.0.113.99"}).status_code == 200


# --------------------------------------------------------- readiness ---------


def test_readiness_probe(client, monkeypatch):
    # Point Redis at a closed port so the check fails fast (connection refused).
    monkeypatch.setattr(settings, "redis_host", "127.0.0.1")
    r = client.get("/health/ready")
    assert r.status_code == 200  # DB (sqlite) is up -> ready
    checks = r.json()["checks"]
    assert checks["database"] == "ok"
    assert checks["redis"] == "down"  # no Redis in the test environment
    assert r.json()["status"] == "ready"


# --------------------------------------------------------- secrets guard -----


def test_insecure_defaults_flagged(monkeypatch):
    problems = settings.insecure_production_defaults()
    assert any("SECRET_KEY" in p for p in problems)
    assert any("BOOTSTRAP_ADMIN_PASSWORD" in p for p in problems)


def test_secure_config_has_no_problems(monkeypatch):
    monkeypatch.setattr(settings, "secret_key", "a" * 64)
    monkeypatch.setattr(settings, "bootstrap_admin_password", "a-strong-password-123")
    monkeypatch.setattr(settings, "postgres_password", "a-strong-db-password")
    monkeypatch.setattr(settings, "cors_origins", "https://crm.example.com")
    monkeypatch.setattr(settings, "debug", False)
    assert settings.insecure_production_defaults() == []


def test_generate_secret_cli(capsys):
    rc = cli.main(["generate-secret"])
    assert rc == 0
    out = capsys.readouterr().out.strip()
    assert len(out) == 64
    int(out, 16)  # valid hex


def test_prod_check_cli_flags_defaults(capsys):
    rc = cli.main(["prod-check"])
    assert rc == 1
    assert "insecure" in capsys.readouterr().out.lower()


def test_prod_check_cli_passes_when_secure(capsys, monkeypatch):
    monkeypatch.setattr(settings, "secret_key", "b" * 64)
    monkeypatch.setattr(settings, "bootstrap_admin_password", "a-strong-password-123")
    monkeypatch.setattr(settings, "postgres_password", "a-strong-db-password")
    monkeypatch.setattr(settings, "cors_origins", "https://crm.example.com")
    monkeypatch.setattr(settings, "debug", False)
    rc = cli.main(["prod-check"])
    assert rc == 0
    assert "looks good" in capsys.readouterr().out.lower()
