"""Phase 6 acceptance: unified live inbox — incoming, live WS, reply, status."""

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


def _logged_in_account(client, token, monkeypatch, label="Inbox Acc") -> int:
    created = client.post(
        "/api/accounts",
        headers=_auth(token),
        json={"label": label, "assign_proxy": False},
    )
    aid = created.json()["id"]

    async def _qr(_id):
        return {"status": "authorized", "url": None, "user": {"id": 7}, "detail": None}

    monkeypatch.setattr(engine_client, "qr_status", _qr)
    client.get(f"/api/accounts/{aid}/login/qr", headers=_auth(token))
    return aid


def _simulate(client, token, account_id, peer_id, text, **kw):
    return client.post(
        "/api/inbox/simulate-incoming",
        headers=_auth(token),
        json={"account_id": account_id, "peer_id": peer_id, "text": text, **kw},
    )


def test_incoming_creates_conversation_and_message(client, admin_token, monkeypatch):
    aid = _logged_in_account(client, admin_token, monkeypatch)
    r = _simulate(client, admin_token, aid, 900001, "hello there", peer_name="Alice")
    assert r.status_code == 200
    conv = r.json()
    assert conv["unread_count"] == 1
    assert conv["last_message_preview"] == "hello there"

    listing = client.get("/api/inbox/conversations", headers=_auth(admin_token)).json()
    assert any(c["id"] == conv["id"] for c in listing)

    thread = client.get(
        f"/api/inbox/conversations/{conv['id']}", headers=_auth(admin_token)
    ).json()
    assert len(thread["messages"]) == 1
    assert thread["messages"][0]["direction"] == "in"
    assert thread["messages"][0]["body"] == "hello there"


def test_mark_read(client, admin_token, monkeypatch):
    aid = _logged_in_account(client, admin_token, monkeypatch)
    conv = _simulate(client, admin_token, aid, 900002, "unread msg").json()
    assert conv["unread_count"] == 1
    read = client.post(
        f"/api/inbox/conversations/{conv['id']}/read", headers=_auth(admin_token)
    )
    assert read.status_code == 200
    assert read.json()["unread_count"] == 0


def test_set_status(client, admin_token, monkeypatch):
    aid = _logged_in_account(client, admin_token, monkeypatch)
    conv = _simulate(client, admin_token, aid, 900003, "hi").json()
    r = client.patch(
        f"/api/inbox/conversations/{conv['id']}",
        headers=_auth(admin_token),
        json={"status": "customer"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "customer"


def test_reply_records_outgoing(client, admin_token, monkeypatch):
    aid = _logged_in_account(client, admin_token, monkeypatch)
    conv = _simulate(client, admin_token, aid, 900004, "question?").json()

    sent = []

    async def _send(account, proxy, target, text):
        sent.append((target, text))
        return {"sent": True}

    monkeypatch.setattr(engine_client, "send_message", _send)
    r = client.post(
        f"/api/inbox/conversations/{conv['id']}/send",
        headers=_auth(admin_token),
        json={"type": "text", "body": "here is the answer"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["direction"] == "out"
    assert body["body"] == "here is the answer"
    assert sent and sent[0] == ("900004", "here is the answer")

    thread = client.get(
        f"/api/inbox/conversations/{conv['id']}", headers=_auth(admin_token)
    ).json()
    assert len(thread["messages"]) == 2


def test_link_detection_on_reply(client, admin_token, monkeypatch):
    aid = _logged_in_account(client, admin_token, monkeypatch)
    conv = _simulate(client, admin_token, aid, 900010, "hi").json()

    async def _send(account, proxy, target, text):
        return {"sent": True}

    monkeypatch.setattr(engine_client, "send_message", _send)
    r = client.post(
        f"/api/inbox/conversations/{conv['id']}/send",
        headers=_auth(admin_token),
        json={"type": "link", "body": "check https://example.com"},
    )
    assert r.json()["type"] == "link"


def test_opt_out_reply_is_honored(client, admin_token, monkeypatch):
    aid = _logged_in_account(client, admin_token, monkeypatch)
    conv = _simulate(client, admin_token, aid, 900005, "STOP").json()
    assert conv["status"] == "opted_out"


def test_incoming_links_contact_and_advances_stage(client, admin_token, monkeypatch):
    aid = _logged_in_account(client, admin_token, monkeypatch)
    contact = client.post(
        "/api/contacts",
        headers=_auth(admin_token),
        json={"username": "@inbox_lead_p6", "consent": True},
    ).json()

    async def _resolve(account, proxy, username):
        return {"user_id": 900777, "status": "resolved"}

    monkeypatch.setattr(engine_client, "resolve_username", _resolve)
    client.post(f"/api/contacts/{contact['id']}/resolve", headers=_auth(admin_token))

    conv = _simulate(client, admin_token, aid, 900777, "I'm interested").json()
    assert conv["contact_id"] == contact["id"]
    assert conv["status"] == "replied"

    refreshed = client.get(
        f"/api/contacts/{contact['id']}", headers=_auth(admin_token)
    ).json()
    assert refreshed["stage"] == "replied"


def test_websocket_receives_incoming(client, admin_token, monkeypatch):
    aid = _logged_in_account(client, admin_token, monkeypatch)
    with client.websocket_connect(f"/ws/inbox?token={admin_token}") as ws:
        hello = ws.receive_json()
        assert hello["type"] == "connected"
        resp = _simulate(client, admin_token, aid, 900006, "live message!", peer_name="Bob")
        assert resp.status_code == 200
        event = ws.receive_json()
        assert event["type"] == "message"
        assert event["message"]["direction"] == "in"
        assert event["message"]["body"] == "live message!"


def test_websocket_rejects_bad_token(client):
    with pytest.raises(Exception):
        with client.websocket_connect("/ws/inbox?token=not-a-token") as ws:
            ws.receive_json()


def test_bulk_read_and_status(client, admin_token, monkeypatch):
    aid = _logged_in_account(client, admin_token, monkeypatch)
    c1 = _simulate(client, admin_token, aid, 900007, "a").json()
    c2 = _simulate(client, admin_token, aid, 900008, "b").json()
    ids = [c1["id"], c2["id"]]

    n = client.post(
        "/api/inbox/bulk/read", headers=_auth(admin_token), json={"conversation_ids": ids}
    )
    assert n.json() == 2
    s = client.post(
        "/api/inbox/bulk/status",
        headers=_auth(admin_token),
        json={"conversation_ids": ids, "status": "joined"},
    )
    assert s.json() == 2
