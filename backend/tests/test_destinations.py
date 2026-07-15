"""Phase 8 acceptance: destinations + Add members (direct-add / invite, exclusion)."""

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


def _logged_in_account(client, token, monkeypatch, label="Dest Acc") -> int:
    created = client.post(
        "/api/accounts", headers=_auth(token), json={"label": label, "assign_proxy": False}
    )
    aid = created.json()["id"]

    async def _qr(_id):
        return {"status": "authorized", "url": None, "user": {"id": 7}, "detail": None}

    monkeypatch.setattr(engine_client, "qr_status", _qr)
    client.get(f"/api/accounts/{aid}/login/qr", headers=_auth(token))
    return aid


def _isolate_via_api(client, token, keep_id):
    for a in client.get("/api/accounts", headers=_auth(token)).json():
        if a["id"] != keep_id and a["session_ref"] and a["status"] == "active":
            client.patch(
                f"/api/accounts/{a['id']}/status", headers=_auth(token),
                json={"status": "logged_out"},
            )


def _register_resolved(client, token, monkeypatch, entity_id=555111, title="My Group"):
    async def _resolve(account, proxy, link):
        return {"tg_entity_id": entity_id, "title": title, "type": "group"}

    monkeypatch.setattr(engine_client, "resolve_destination", _resolve)
    r = client.post(
        "/api/destinations", headers=_auth(token),
        json={"link": "https://t.me/mygroup"},
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_register_resolves_destination(client, admin_token, monkeypatch):
    _logged_in_account(client, admin_token, monkeypatch)
    dest = _register_resolved(client, admin_token, monkeypatch)
    assert dest["tg_entity_id"] == 555111
    assert dest["title"] == "My Group"
    assert dest["type"] == "group"


def test_register_unresolved_when_engine_down(client, admin_token, monkeypatch):
    _logged_in_account(client, admin_token, monkeypatch)

    async def _boom(account, proxy, link):
        raise engine_client.EngineUnavailable("down")

    monkeypatch.setattr(engine_client, "resolve_destination", _boom)
    r = client.post(
        "/api/destinations", headers=_auth(admin_token),
        json={"link": "https://t.me/unresolved"},
    )
    assert r.status_code == 201
    assert r.json()["tg_entity_id"] is None
    assert r.json()["type"] == "unknown"


def test_add_members_filters_consent_and_typed(client, admin_token, monkeypatch):
    _logged_in_account(client, admin_token, monkeypatch)
    dest = _register_resolved(client, admin_token, monkeypatch, entity_id=600001)

    consented = client.post(
        "/api/contacts", headers=_auth(admin_token),
        json={"username": "@d8_ok", "consent": True},
    ).json()
    no_consent = client.post(
        "/api/contacts", headers=_auth(admin_token),
        json={"username": "@d8_noc", "consent": False},
    ).json()

    r = client.post(
        f"/api/destinations/{dest['id']}/add-members",
        headers=_auth(admin_token),
        json={
            "contact_ids": [consented["id"], no_consent["id"]],
            "identifiers": ["@d8_typed", "+15550007777"],
        },
    )
    assert r.status_code == 200
    # 1 consented contact + 2 typed = 3; the no-consent contact is excluded.
    assert r.json()["queued"] == 3


def test_add_tick_direct_add(client, admin_token, monkeypatch):
    aid = _logged_in_account(client, admin_token, monkeypatch, label="Add Acc")
    _isolate_via_api(client, admin_token, aid)
    dest = _register_resolved(client, admin_token, monkeypatch, entity_id=600002)
    contact = client.post(
        "/api/contacts", headers=_auth(admin_token),
        json={"username": "@d8_add", "consent": True},
    ).json()
    client.post(
        f"/api/destinations/{dest['id']}/add-members",
        headers=_auth(admin_token), json={"contact_ids": [contact["id"]]},
    )

    async def _add(account, proxy, entity_id, target):
        return {"state": "added", "method": "direct_add"}

    monkeypatch.setattr(engine_client, "add_member", _add)
    tick = client.post(
        f"/api/destinations/{dest['id']}/add-members/tick", headers=_auth(admin_token)
    )
    assert tick.status_code == 200
    assert tick.json()["added"] == 1

    detail = client.get(f"/api/destinations/{dest['id']}", headers=_auth(admin_token)).json()
    assert detail["stats"]["added"] == 1
    assert detail["memberships"][0]["method"] == "direct_add"


def test_add_tick_invite_fallback(client, admin_token, monkeypatch):
    aid = _logged_in_account(client, admin_token, monkeypatch, label="Invite Acc")
    _isolate_via_api(client, admin_token, aid)
    dest = _register_resolved(client, admin_token, monkeypatch, entity_id=600003)
    contact = client.post(
        "/api/contacts", headers=_auth(admin_token),
        json={"username": "@d8_invite", "consent": True},
    ).json()
    client.post(
        f"/api/destinations/{dest['id']}/add-members",
        headers=_auth(admin_token), json={"contact_ids": [contact["id"]]},
    )

    async def _add(account, proxy, entity_id, target):
        return {"state": "invited", "method": "invite", "invite_link": "https://t.me/+abc"}

    monkeypatch.setattr(engine_client, "add_member", _add)
    tick = client.post(
        f"/api/destinations/{dest['id']}/add-members/tick", headers=_auth(admin_token)
    )
    assert tick.json()["invited"] == 1


def test_already_member_excluded_and_filterable(client, admin_token, monkeypatch):
    aid = _logged_in_account(client, admin_token, monkeypatch, label="Excl Acc")
    _isolate_via_api(client, admin_token, aid)
    dest = _register_resolved(client, admin_token, monkeypatch, entity_id=600004)
    contact = client.post(
        "/api/contacts", headers=_auth(admin_token),
        json={"username": "@d8_excl", "consent": True},
    ).json()
    client.post(
        f"/api/destinations/{dest['id']}/add-members",
        headers=_auth(admin_token), json={"contact_ids": [contact["id"]]},
    )

    async def _add(account, proxy, entity_id, target):
        return {"state": "added", "method": "direct_add"}

    monkeypatch.setattr(engine_client, "add_member", _add)
    client.post(f"/api/destinations/{dest['id']}/add-members/tick", headers=_auth(admin_token))

    # Re-adding the same contact is excluded (already in destination).
    again = client.post(
        f"/api/destinations/{dest['id']}/add-members",
        headers=_auth(admin_token), json={"contact_ids": [contact["id"]]},
    )
    assert again.json()["queued"] == 0
    assert again.json()["skipped_existing"] == 1

    # The contact is excluded by the not_in_destination filter.
    excluded = client.get(
        f"/api/contacts?not_in_destination={dest['id']}", headers=_auth(admin_token)
    ).json()
    assert all(c["id"] != contact["id"] for c in excluded)
    # ...and present in the in_destination filter.
    included = client.get(
        f"/api/contacts?in_destination={dest['id']}", headers=_auth(admin_token)
    ).json()
    assert any(c["id"] == contact["id"] for c in included)


def test_add_tick_flood_quarantines(client, admin_token, monkeypatch):
    aid = _logged_in_account(client, admin_token, monkeypatch, label="Flood Add")
    _isolate_via_api(client, admin_token, aid)
    dest = _register_resolved(client, admin_token, monkeypatch, entity_id=600005)
    contact = client.post(
        "/api/contacts", headers=_auth(admin_token),
        json={"username": "@d8_flood", "consent": True},
    ).json()
    client.post(
        f"/api/destinations/{dest['id']}/add-members",
        headers=_auth(admin_token), json={"contact_ids": [contact["id"]]},
    )

    async def _add(account, proxy, entity_id, target):
        return {"state": "failed", "error": "peerflood"}

    monkeypatch.setattr(engine_client, "add_member", _add)
    tick = client.post(
        f"/api/destinations/{dest['id']}/add-members/tick", headers=_auth(admin_token)
    )
    assert tick.json()["paused"] is True

    account = client.get(f"/api/accounts/{aid}", headers=_auth(admin_token)).json()
    assert account["status"] == "quarantined"
    # The membership stays pending for a later retry.
    detail = client.get(f"/api/destinations/{dest['id']}", headers=_auth(admin_token)).json()
    assert detail["stats"]["pending"] == 1


def test_tick_requires_resolved(client, admin_token, monkeypatch):
    _logged_in_account(client, admin_token, monkeypatch)

    async def _boom(account, proxy, link):
        raise engine_client.EngineUnavailable("down")

    monkeypatch.setattr(engine_client, "resolve_destination", _boom)
    dest = client.post(
        "/api/destinations", headers=_auth(admin_token),
        json={"link": "https://t.me/notresolved"},
    ).json()
    r = client.post(
        f"/api/destinations/{dest['id']}/add-members/tick", headers=_auth(admin_token)
    )
    assert r.status_code == 400


def test_agent_cannot_access_destinations(client, admin_token):
    client.post(
        "/api/users", headers=_auth(admin_token),
        json={"email": "agent8@test.com", "password": "AgentPass123", "role": "agent"},
    )
    agent = _login(client, "agent8@test.com", "AgentPass123")
    assert client.get("/api/destinations", headers=_auth(agent)).status_code == 403
