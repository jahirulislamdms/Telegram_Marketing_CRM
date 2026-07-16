"""Phase 15.1.h/i/j — retention, archive/unarchive, delete, and the Archive folder."""

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


def _logged_in_account(client, token, monkeypatch, label) -> int:
    created = client.post(
        "/api/accounts", headers=_auth(token), json={"label": label, "assign_proxy": False}
    )
    aid = created.json()["id"]

    async def _qr(_id):
        return {"status": "authorized", "url": None, "user": {"id": 7}, "detail": None}

    monkeypatch.setattr(engine_client, "qr_status", _qr)
    client.get(f"/api/accounts/{aid}/login/qr", headers=_auth(token))
    return aid


def _simulate(client, token, aid, **kw):
    return client.post(
        "/api/inbox/simulate-incoming", headers=_auth(token), json={"account_id": aid, **kw}
    )


def _ids(client, token, aid, archived=False) -> set:
    suffix = "&archived=true" if archived else ""
    res = client.get(
        f"/api/inbox/conversations?account_ids={aid}{suffix}", headers=_auth(token)
    ).json()
    return {c["id"] for c in res}


# --------------------------------------------- 15.1.i/j: archive & folder ----


def test_archive_moves_chat_to_archive_folder_and_back(client, admin_token, monkeypatch):
    aid = _logged_in_account(client, admin_token, monkeypatch, "Arch Acct")
    conv = _simulate(client, admin_token, aid, peer_id=820001, peer_name="Archie", text="hi").json()
    cid = conv["id"]
    assert conv["archived"] is False
    assert cid in _ids(client, admin_token, aid)  # in the main inbox

    # Archive -> leaves the inbox, appears in the Archive folder, history kept.
    r = client.post(
        f"/api/inbox/conversations/{cid}/archive", headers=_auth(admin_token),
        json={"archived": True},
    )
    assert r.status_code == 200, r.text
    assert r.json()["archived"] is True
    assert cid not in _ids(client, admin_token, aid)
    assert cid in _ids(client, admin_token, aid, archived=True)

    # History survives archiving.
    thread = client.get(f"/api/inbox/conversations/{cid}", headers=_auth(admin_token)).json()
    assert thread["messages"][-1]["body"] == "hi"

    # Unarchive -> back to the inbox.
    r = client.post(
        f"/api/inbox/conversations/{cid}/archive", headers=_auth(admin_token),
        json={"archived": False},
    )
    assert r.json()["archived"] is False
    assert cid in _ids(client, admin_token, aid)
    assert cid not in _ids(client, admin_token, aid, archived=True)


# ------------------------------------------------------- 15.1.i: delete ------


def test_delete_removes_conversation_and_messages(client, admin_token, monkeypatch):
    aid = _logged_in_account(client, admin_token, monkeypatch, "Del Acct")
    conv = _simulate(client, admin_token, aid, peer_id=820002, peer_name="Deleteme", text="bye").json()
    cid = conv["id"]

    r = client.delete(f"/api/inbox/conversations/{cid}", headers=_auth(admin_token))
    assert r.status_code == 204, r.text
    assert cid not in _ids(client, admin_token, aid)
    assert cid not in _ids(client, admin_token, aid, archived=True)
    # Thread is gone (messages removed with it).
    assert client.get(
        f"/api/inbox/conversations/{cid}", headers=_auth(admin_token)
    ).status_code == 404


def test_agent_cannot_delete_conversation(client, admin_token, monkeypatch):
    aid = _logged_in_account(client, admin_token, monkeypatch, "Del RBAC Acct")
    conv = _simulate(client, admin_token, aid, peer_id=820003, peer_name="Safe", text="hi").json()
    client.post(
        "/api/users", headers=_auth(admin_token),
        json={"email": "agent15@test.com", "password": "AgentPass123", "role": "agent"},
    )
    agent = _login(client, "agent15@test.com", "AgentPass123")
    r = client.delete(f"/api/inbox/conversations/{conv['id']}", headers=_auth(agent))
    assert r.status_code == 403
    # Still there.
    assert client.get(
        f"/api/inbox/conversations/{conv['id']}", headers=_auth(admin_token)
    ).status_code == 200


# --------------------------------------------------- 15.1.h: retention -------


def test_history_survives_peer_deleting_on_telegram(client, admin_token, monkeypatch):
    """The CRM is the system of record: a peer-side delete never removes our copy."""
    aid = _logged_in_account(client, admin_token, monkeypatch, "Retain Acct")
    conv = _simulate(
        client, admin_token, aid,
        peer_id=820004, peer_name="Ghost", msg_type="image", media_ref="{}",
        text="look at this", tg_message_id=4321,
    ).json()
    cid = conv["id"]
    mid = client.get(f"/api/inbox/conversations/{cid}", headers=_auth(admin_token)).json()[
        "messages"
    ][-1]["id"]

    # The peer deletes it on Telegram -> the engine can no longer fetch the media.
    async def _gone(account, proxy, peer, message_id):
        return None

    monkeypatch.setattr(engine_client, "download_media", _gone)
    assert client.get(
        f"/api/inbox/messages/{mid}/media", headers=_auth(admin_token)
    ).status_code == 404  # UI shows "media no longer available"

    # ...but the message, its text, and the conversation all remain.
    thread = client.get(f"/api/inbox/conversations/{cid}", headers=_auth(admin_token)).json()
    msg = thread["messages"][-1]
    assert msg["id"] == mid
    assert msg["body"] == "look at this"
    assert msg["type"] == "image"
    assert cid in _ids(client, admin_token, aid)
