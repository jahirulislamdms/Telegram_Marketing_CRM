"""Phase 15.1.b — inbound media: recording + on-demand streaming from Telegram."""

import json

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


def _logged_in_account(client, token, monkeypatch, label="Media Acc") -> int:
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
    body = {"account_id": aid, "peer_name": "Media Peer", **kw}
    return client.post("/api/inbox/simulate-incoming", headers=_auth(token), json=body)


def _last_message(client, token, conv_id) -> dict:
    thread = client.get(f"/api/inbox/conversations/{conv_id}", headers=_auth(token)).json()
    return thread["messages"][-1]


def test_incoming_media_recorded_with_type_and_meta(client, admin_token, monkeypatch):
    aid = _logged_in_account(client, admin_token, monkeypatch)
    meta = json.dumps({"kind": "image", "mime": "image/jpeg", "name": "photo.jpg", "size": 2048})
    r = _simulate(
        client, admin_token, aid,
        peer_id=6543211, msg_type="image", media_ref=meta, tg_message_id=555,
    )
    assert r.status_code == 200, r.text
    conv_id = r.json()["id"]

    # No caption -> the conversation preview shows a media tag.
    convs = client.get("/api/inbox/conversations", headers=_auth(admin_token)).json()
    conv = next(c for c in convs if c["id"] == conv_id)
    assert conv["last_message_preview"] == "[image]"

    msg = _last_message(client, admin_token, conv_id)
    assert msg["type"] == "image"
    assert json.loads(msg["media_ref"])["name"] == "photo.jpg"


def test_media_endpoint_streams_bytes_from_engine(client, admin_token, monkeypatch):
    aid = _logged_in_account(client, admin_token, monkeypatch, label="Media Acc 2")
    r = _simulate(
        client, admin_token, aid,
        peer_id=6543212, msg_type="image", media_ref="{}", tg_message_id=777,
    )
    mid = _last_message(client, admin_token, r.json()["id"])["id"]

    async def _dl(account, proxy, peer, message_id):
        assert str(peer) == "6543212"
        assert message_id == 777
        return {"bytes": b"\x89PNG\r\nFAKEBYTES", "mime": "image/png", "name": "pic.png"}

    monkeypatch.setattr(engine_client, "download_media", _dl)

    resp = client.get(f"/api/inbox/messages/{mid}/media", headers=_auth(admin_token))
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("image/png")
    assert resp.content == b"\x89PNG\r\nFAKEBYTES"
    assert "inline" in resp.headers.get("content-disposition", "")


def test_file_media_served_as_attachment(client, admin_token, monkeypatch):
    aid = _logged_in_account(client, admin_token, monkeypatch, label="Media Acc 5")
    meta = json.dumps({"kind": "file", "name": "report.pdf"})
    r = _simulate(
        client, admin_token, aid,
        peer_id=6543215, msg_type="file", media_ref=meta, tg_message_id=999,
    )
    mid = _last_message(client, admin_token, r.json()["id"])["id"]

    async def _dl(account, proxy, peer, message_id):
        return {"bytes": b"%PDF-1.4 fake", "mime": "application/pdf", "name": "report.pdf"}

    monkeypatch.setattr(engine_client, "download_media", _dl)
    resp = client.get(f"/api/inbox/messages/{mid}/media", headers=_auth(admin_token))
    assert resp.status_code == 200
    assert "attachment" in resp.headers.get("content-disposition", "")
    assert "report.pdf" in resp.headers.get("content-disposition", "")


def test_media_endpoint_404_when_peer_deleted(client, admin_token, monkeypatch):
    aid = _logged_in_account(client, admin_token, monkeypatch, label="Media Acc 3")
    r = _simulate(
        client, admin_token, aid,
        peer_id=6543213, msg_type="video", media_ref="{}", tg_message_id=888,
    )
    mid = _last_message(client, admin_token, r.json()["id"])["id"]

    async def _dl(account, proxy, peer, message_id):
        return None  # gone from Telegram

    monkeypatch.setattr(engine_client, "download_media", _dl)
    resp = client.get(f"/api/inbox/messages/{mid}/media", headers=_auth(admin_token))
    assert resp.status_code == 404


def test_media_endpoint_404_for_text_message(client, admin_token, monkeypatch):
    aid = _logged_in_account(client, admin_token, monkeypatch, label="Media Acc 4")
    r = _simulate(client, admin_token, aid, peer_id=6543214, text="just text")
    mid = _last_message(client, admin_token, r.json()["id"])["id"]
    resp = client.get(f"/api/inbox/messages/{mid}/media", headers=_auth(admin_token))
    assert resp.status_code == 404
