"""Phase 15.6 — Telegram account identity capture + the unified Edit endpoint."""

import pytest

from app.services import engine_client


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _login(client, email, password) -> str:
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture()
def admin_token(client, admin_credentials) -> str:
    return _login(client, **admin_credentials)


@pytest.fixture(autouse=True)
def _release_proxies(client, admin_credentials):
    """Give back any proxy this module's accounts took.

    The test DB is shared across files and other suites assert on global proxy
    assignment counts, so §15.6 must leave the pool as it found it.
    """
    yield
    token = _login(client, **admin_credentials)
    for a in client.get("/api/accounts", headers=_auth(token)).json():
        if a["proxy_id"] is not None and str(a["label"]).startswith("p156-"):
            client.patch(
                f"/api/accounts/{a['id']}",
                headers=_auth(token),
                json={"assign_proxy": False},
            )


def _create(client, token, label, assign_proxy=False) -> dict:
    r = client.post(
        "/api/accounts",
        headers=_auth(token),
        json={"label": label, "assign_proxy": assign_proxy},
    )
    assert r.status_code == 201, r.text
    return r.json()


# ------------------------------------------------------------- identity ------


def test_login_captures_telegram_identity(client, admin_token, monkeypatch):
    acct = _create(client, admin_token, "p156-identity-1")

    async def _qr(_id):
        return {
            "status": "authorized",
            "url": None,
            "user": {
                "id": 777001,
                "username": "@RealHandle",
                "first_name": "Sales Bot",
                "phone": "8801700000001",
            },
            "detail": None,
        }

    monkeypatch.setattr(engine_client, "qr_status", _qr)
    client.get(f"/api/accounts/{acct['id']}/login/qr", headers=_auth(admin_token))

    got = client.get(f"/api/accounts/{acct['id']}", headers=_auth(admin_token)).json()
    assert got["tg_user_id"] == 777001
    assert got["tg_username"] == "RealHandle"      # '@' stripped
    assert got["tg_first_name"] == "Sales Bot"
    assert got["phone"] == "+8801700000001"        # '+' added by the identity capture
    assert got["label"] == "p156-identity-1"            # our own label is never overwritten
    assert got["session_ref"]                      # login still works exactly as before


def test_identity_capture_does_not_overwrite_operator_phone(client, admin_token, monkeypatch):
    r = client.post(
        "/api/accounts",
        headers=_auth(admin_token),
        json={"label": "p156-identity-2", "phone": "+15550001111", "assign_proxy": False},
    )
    acct = r.json()

    async def _qr(_id):
        return {
            "status": "authorized", "url": None,
            "user": {"id": 777002, "phone": "9999999999"}, "detail": None,
        }

    monkeypatch.setattr(engine_client, "qr_status", _qr)
    client.get(f"/api/accounts/{acct['id']}/login/qr", headers=_auth(admin_token))
    got = client.get(f"/api/accounts/{acct['id']}", headers=_auth(admin_token)).json()
    assert got["phone"] == "+15550001111"  # operator-entered phone wins
    assert got["tg_user_id"] == 777002


def test_status_check_refreshes_identity(client, admin_token, monkeypatch):
    acct = _create(client, admin_token, "p156-identity-3")

    async def _status(_id):
        return {
            "connected": True,
            "authorized": True,
            "user": {"id": 777003, "username": "refreshed_handle", "first_name": "Refreshed"},
        }

    monkeypatch.setattr(engine_client, "get_status", _status)
    r = client.get(f"/api/accounts/{acct['id']}/status", headers=_auth(admin_token))
    assert r.status_code == 200
    got = client.get(f"/api/accounts/{acct['id']}", headers=_auth(admin_token)).json()
    assert got["tg_username"] == "refreshed_handle"
    assert got["tg_user_id"] == 777003


def test_identity_absent_when_engine_reports_none(client, admin_token, monkeypatch):
    acct = _create(client, admin_token, "p156-identity-4")

    async def _qr(_id):
        return {"status": "authorized", "url": None, "user": None, "detail": None}

    monkeypatch.setattr(engine_client, "qr_status", _qr)
    client.get(f"/api/accounts/{acct['id']}/login/qr", headers=_auth(admin_token))
    got = client.get(f"/api/accounts/{acct['id']}", headers=_auth(admin_token)).json()
    assert got["tg_user_id"] is None
    assert got["tg_username"] is None
    assert got["session_ref"]  # login itself is unaffected


# --------------------------------------------------------- unified edit ------


def test_edit_renames_account(client, admin_token):
    acct = _create(client, admin_token, "p156-old-name")
    r = client.patch(
        f"/api/accounts/{acct['id']}", headers=_auth(admin_token), json={"label": "p156-New Name"}
    )
    assert r.status_code == 200, r.text
    assert r.json()["label"] == "p156-New Name"


def test_edit_rejects_blank_name(client, admin_token):
    acct = _create(client, admin_token, "p156-keeps-name")
    r = client.patch(
        f"/api/accounts/{acct['id']}", headers=_auth(admin_token), json={"label": "   "}
    )
    assert r.status_code == 422
    assert r.json()["detail"] == "Account name cannot be empty."


def test_edit_assigns_and_releases_proxy(client, admin_token):
    client.post(
        "/api/proxies/import",
        headers=_auth(admin_token),
        json={"raw": "10.15.6.1:1080\n10.15.6.2:1080"},
    )
    acct = _create(client, admin_token, "p156-proxy-edit", assign_proxy=False)
    assert acct["proxy_id"] is None

    # Enable proxy without naming one -> auto-assign a free proxy.
    on = client.patch(
        f"/api/accounts/{acct['id']}", headers=_auth(admin_token), json={"assign_proxy": True}
    ).json()
    assert on["proxy_id"] is not None
    assigned = on["proxy_id"]

    # Disable -> released back to the pool.
    off = client.patch(
        f"/api/accounts/{acct['id']}", headers=_auth(admin_token), json={"assign_proxy": False}
    ).json()
    assert off["proxy_id"] is None
    pool = client.get("/api/proxies", headers=_auth(admin_token)).json()
    freed = next(p for p in pool if p["id"] == assigned)
    assert freed["assigned_account_id"] is None


def test_edit_selects_a_specific_proxy(client, admin_token):
    client.post(
        "/api/proxies/import",
        headers=_auth(admin_token),
        json={"raw": "10.15.6.10:1080\n10.15.6.11:1080"},
    )
    pool = client.get("/api/proxies", headers=_auth(admin_token)).json()
    free = [p for p in pool if p["assigned_account_id"] is None]
    target = free[-1]
    acct = _create(client, admin_token, "p156-proxy-pick", assign_proxy=False)

    r = client.patch(
        f"/api/accounts/{acct['id']}",
        headers=_auth(admin_token),
        json={"assign_proxy": True, "proxy_id": target["id"]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["proxy_id"] == target["id"]


def test_edit_rejects_proxy_taken_by_another_account(client, admin_token):
    client.post(
        "/api/proxies/import",
        headers=_auth(admin_token),
        json={"raw": "10.15.6.20:1080"},
    )
    pool = client.get("/api/proxies", headers=_auth(admin_token)).json()
    target = next(p for p in pool if p["host"] == "10.15.6.20")
    a = _create(client, admin_token, "p156-owner-acct", assign_proxy=False)
    b = _create(client, admin_token, "p156-other-acct", assign_proxy=False)

    client.patch(
        f"/api/accounts/{a['id']}",
        headers=_auth(admin_token),
        json={"assign_proxy": True, "proxy_id": target["id"]},
    )
    r = client.patch(
        f"/api/accounts/{b['id']}",
        headers=_auth(admin_token),
        json={"assign_proxy": True, "proxy_id": target["id"]},
    )
    assert r.status_code == 409
    assert "already assigned" in r.json()["detail"]


def test_edit_label_and_proxy_together(client, admin_token):
    client.post(
        "/api/proxies/import", headers=_auth(admin_token), json={"raw": "10.15.6.30:1080"}
    )
    acct = _create(client, admin_token, "p156-combo-before", assign_proxy=False)
    r = client.patch(
        f"/api/accounts/{acct['id']}",
        headers=_auth(admin_token),
        json={"label": "p156-combo-after", "assign_proxy": True},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["label"] == "p156-combo-after"
    assert body["proxy_id"] is not None


def test_edit_requires_manager(client, admin_token):
    acct = _create(client, admin_token, "p156-rbac-acct")
    client.post(
        "/api/users",
        headers=_auth(admin_token),
        json={"email": "agent156@test.com", "password": "AgentPass123", "role": "agent"},
    )
    agent = _login(client, "agent156@test.com", "AgentPass123")
    r = client.patch(
        f"/api/accounts/{acct['id']}", headers=_auth(agent), json={"label": "p156-nope"}
    )
    assert r.status_code == 403
