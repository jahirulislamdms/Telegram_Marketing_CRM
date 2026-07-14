"""Phase 2 acceptance: account CRUD, proxy pool, RBAC, and engine delegation.

The Telegram engine is mocked here — real QR/phone login needs live Telegram
credentials and cannot run in CI.
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


def test_agent_cannot_access_accounts(client, admin_token):
    # Create an agent, then confirm the agent is forbidden from the account manager.
    created = client.post(
        "/api/users",
        headers=_auth(admin_token),
        json={"email": "agent2@test.com", "password": "AgentPass123", "role": "agent"},
    )
    assert created.status_code == 201
    agent_token = _login(client, "agent2@test.com", "AgentPass123")
    assert client.get("/api/accounts", headers=_auth(agent_token)).status_code == 403


def test_create_and_list_account(client, admin_token):
    resp = client.post(
        "/api/accounts",
        headers=_auth(admin_token),
        json={"label": "Sales 1", "phone": "+10000000001", "assign_proxy": False},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["label"] == "Sales 1"
    assert body["status"] == "logged_out"
    assert body["session_ref"] is None

    listing = client.get("/api/accounts", headers=_auth(admin_token))
    assert listing.status_code == 200
    assert any(a["label"] == "Sales 1" for a in listing.json())


def test_proxy_import_and_auto_assign(client, admin_token):
    imported = client.post(
        "/api/proxies/import",
        headers=_auth(admin_token),
        json={
            "raw": "10.0.0.1:1080\n10.0.0.1:1080\nsocks5://u:p@10.0.0.2:1080\nbroken-line"
        },
    )
    assert imported.status_code == 200
    result = imported.json()
    assert result["imported"] == 2  # one duplicate, one invalid
    assert result["skipped_duplicates"] == 1
    assert result["invalid"] == ["broken-line"]

    # Creating an account with assign_proxy should bind a free proxy.
    created = client.post(
        "/api/accounts",
        headers=_auth(admin_token),
        json={"label": "With Proxy", "assign_proxy": True},
    )
    assert created.status_code == 201
    assert created.json()["proxy_id"] is not None

    proxies = client.get("/api/proxies", headers=_auth(admin_token)).json()
    assigned = [p for p in proxies if p["assigned_account_id"] is not None]
    assert len(assigned) == 1


def test_status_when_engine_unreachable(client, admin_token, monkeypatch):
    created = client.post(
        "/api/accounts",
        headers=_auth(admin_token),
        json={"label": "Status Test", "assign_proxy": False},
    )
    account_id = created.json()["id"]

    async def _boom(_account_id):
        raise engine_client.EngineUnavailable("connection refused")

    monkeypatch.setattr(engine_client, "get_status", _boom)
    resp = client.get(f"/api/accounts/{account_id}/status", headers=_auth(admin_token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["engine_reachable"] is False
    assert body["connected"] is False


def test_status_with_engine_mocked(client, admin_token, monkeypatch):
    created = client.post(
        "/api/accounts",
        headers=_auth(admin_token),
        json={"label": "Live", "assign_proxy": False},
    )
    account_id = created.json()["id"]

    async def _status(_account_id):
        return {
            "connected": True,
            "authorized": True,
            "user": {"id": 555, "username": "bot"},
        }

    monkeypatch.setattr(engine_client, "get_status", _status)
    resp = client.get(f"/api/accounts/{account_id}/status", headers=_auth(admin_token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["engine_reachable"] is True
    assert body["authorized"] is True
    assert body["telegram_user"]["id"] == 555


def test_qr_start_delegates_to_engine(client, admin_token, monkeypatch):
    created = client.post(
        "/api/accounts",
        headers=_auth(admin_token),
        json={"label": "QR", "assign_proxy": False},
    )
    account_id = created.json()["id"]

    async def _qr_start(account, proxy):
        return {"url": "tg://login?token=abc", "expires_at": None}

    monkeypatch.setattr(engine_client, "qr_start", _qr_start)
    resp = client.post(f"/api/accounts/{account_id}/login/qr", headers=_auth(admin_token))
    assert resp.status_code == 200
    assert resp.json()["url"] == "tg://login?token=abc"


def test_qr_authorized_marks_logged_in(client, admin_token, monkeypatch):
    created = client.post(
        "/api/accounts",
        headers=_auth(admin_token),
        json={"label": "QR Auth", "assign_proxy": False},
    )
    account_id = created.json()["id"]

    async def _qr_status(_account_id):
        return {
            "status": "authorized",
            "url": None,
            "user": {"id": 1, "username": "u"},
            "detail": None,
        }

    monkeypatch.setattr(engine_client, "qr_status", _qr_status)
    resp = client.get(f"/api/accounts/{account_id}/login/qr", headers=_auth(admin_token))
    assert resp.status_code == 200

    # The account should now be marked active with a session reference.
    account = client.get(f"/api/accounts/{account_id}", headers=_auth(admin_token)).json()
    assert account["status"] == "active"
    assert account["session_ref"] is not None


def test_delete_account(client, admin_token, monkeypatch):
    created = client.post(
        "/api/accounts",
        headers=_auth(admin_token),
        json={"label": "Temp", "assign_proxy": False},
    )
    account_id = created.json()["id"]

    async def _logout(_account_id):
        return {"status": "logged_out"}

    monkeypatch.setattr(engine_client, "logout", _logout)
    resp = client.delete(f"/api/accounts/{account_id}", headers=_auth(admin_token))
    assert resp.status_code == 204
    gone = client.get(f"/api/accounts/{account_id}", headers=_auth(admin_token))
    assert gone.status_code == 404
