"""Phase 3 acceptance: account health checks, manual override, auto-quarantine.

The engine is mocked (real @SpamBot needs a live authorized account).
"""

import pytest

from app.services import engine_client


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _login(client, email: str, password: str) -> str:
    resp = client.post("/api/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


@pytest.fixture()
def admin_token(client, admin_credentials) -> str:
    return _login(client, **admin_credentials)


def _make_logged_in_account(client, token, monkeypatch, label="Health Acc") -> int:
    created = client.post(
        "/api/accounts",
        headers=_auth(token),
        json={"label": label, "assign_proxy": False},
    )
    account_id = created.json()["id"]

    async def _qr_status(_account_id):
        return {"status": "authorized", "url": None, "user": {"id": 7}, "detail": None}

    monkeypatch.setattr(engine_client, "qr_status", _qr_status)
    resp = client.get(f"/api/accounts/{account_id}/login/qr", headers=_auth(token))
    assert resp.status_code == 200
    return account_id


def test_spam_check_clean_does_not_quarantine(client, admin_token, monkeypatch):
    account_id = _make_logged_in_account(client, admin_token, monkeypatch)

    async def _spam(account, proxy):
        return {"spam_state": "clean", "reply": "no limits are currently applied"}

    monkeypatch.setattr(engine_client, "spam_check", _spam)
    resp = client.post(
        f"/api/accounts/{account_id}/health/spam-check", headers=_auth(admin_token)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["spam_state"] == "clean"
    assert body["quarantined"] is False

    account = client.get(
        f"/api/accounts/{account_id}", headers=_auth(admin_token)
    ).json()
    assert account["status"] == "active"
    assert account["spam_state"] == "clean"


def test_spam_check_limited_auto_quarantines(client, admin_token, monkeypatch):
    account_id = _make_logged_in_account(client, admin_token, monkeypatch)

    async def _spam(account, proxy):
        return {"spam_state": "limited", "reply": "your account is now limited"}

    monkeypatch.setattr(engine_client, "spam_check", _spam)
    resp = client.post(
        f"/api/accounts/{account_id}/health/spam-check", headers=_auth(admin_token)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["spam_state"] == "limited"
    assert body["quarantined"] is True

    account = client.get(
        f"/api/accounts/{account_id}", headers=_auth(admin_token)
    ).json()
    assert account["status"] == "quarantined"


def test_ban_check_marks_banned(client, admin_token, monkeypatch):
    account_id = _make_logged_in_account(client, admin_token, monkeypatch)

    async def _ban(account, proxy):
        return {"state": "banned", "user": None}

    monkeypatch.setattr(engine_client, "ban_check", _ban)
    resp = client.post(
        f"/api/accounts/{account_id}/health/ban-check", headers=_auth(admin_token)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] == "banned"
    assert body["status"] == "banned"


def test_ban_check_unauthorized_logs_out(client, admin_token, monkeypatch):
    account_id = _make_logged_in_account(client, admin_token, monkeypatch)

    async def _ban(account, proxy):
        return {"state": "unauthorized", "user": None}

    monkeypatch.setattr(engine_client, "ban_check", _ban)
    resp = client.post(
        f"/api/accounts/{account_id}/health/ban-check", headers=_auth(admin_token)
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "logged_out"
    account = client.get(
        f"/api/accounts/{account_id}", headers=_auth(admin_token)
    ).json()
    assert account["session_ref"] is None


def test_health_check_requires_login(client, admin_token):
    created = client.post(
        "/api/accounts",
        headers=_auth(admin_token),
        json={"label": "Fresh", "assign_proxy": False},
    )
    account_id = created.json()["id"]
    resp = client.post(
        f"/api/accounts/{account_id}/health/spam-check", headers=_auth(admin_token)
    )
    assert resp.status_code == 400


def test_manual_status_override(client, admin_token):
    created = client.post(
        "/api/accounts",
        headers=_auth(admin_token),
        json={"label": "Override", "assign_proxy": False},
    )
    account_id = created.json()["id"]

    resp = client.patch(
        f"/api/accounts/{account_id}/status",
        headers=_auth(admin_token),
        json={"status": "quarantined"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "quarantined"

    # Invalid status is rejected by validation.
    bad = client.patch(
        f"/api/accounts/{account_id}/status",
        headers=_auth(admin_token),
        json={"status": "not-a-status"},
    )
    assert bad.status_code == 422


def test_unspam_request(client, admin_token, monkeypatch):
    account_id = _make_logged_in_account(client, admin_token, monkeypatch)

    async def _unspam(account, proxy):
        return {"submitted": True, "reply": "appeal received"}

    monkeypatch.setattr(engine_client, "request_unspam", _unspam)
    resp = client.post(
        f"/api/accounts/{account_id}/health/unspam", headers=_auth(admin_token)
    )
    assert resp.status_code == 200
    assert resp.json()["submitted"] is True


def test_agent_cannot_run_health(client, admin_token, monkeypatch):
    account_id = _make_logged_in_account(client, admin_token, monkeypatch)
    client.post(
        "/api/users",
        headers=_auth(admin_token),
        json={"email": "agent3@test.com", "password": "AgentPass123", "role": "agent"},
    )
    agent_token = _login(client, "agent3@test.com", "AgentPass123")
    resp = client.post(
        f"/api/accounts/{account_id}/health/spam-check", headers=_auth(agent_token)
    )
    assert resp.status_code == 403
