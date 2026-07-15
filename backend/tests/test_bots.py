"""Phase 10 acceptance: multi-bot console (host, bot inbox, reply, post, broadcast)."""

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


@pytest.fixture()
def bot(client, admin_token, monkeypatch):
    async def _info(token):
        return {"name": "Demo Bot", "username": "demo_bot"}

    monkeypatch.setattr(engine_client, "bot_info", _info)
    r = client.post("/api/bots", headers=_auth(admin_token), json={"token": "123:ABCDEF"})
    assert r.status_code == 201, r.text
    return r.json()


def test_add_and_start_stop_bot(client, admin_token, bot, monkeypatch):
    assert bot["username"] == "demo_bot"
    assert bot["status"] == "stopped"

    async def _start(bot_id, token):
        return {"username": "demo_bot", "name": "Demo Bot", "running": True}

    async def _stop(bot_id, token=""):
        return {"running": False}

    monkeypatch.setattr(engine_client, "bot_start", _start)
    monkeypatch.setattr(engine_client, "bot_stop", _stop)

    started = client.post(f"/api/bots/{bot['id']}/start", headers=_auth(admin_token))
    assert started.json()["status"] == "running"
    stopped = client.post(f"/api/bots/{bot['id']}/stop", headers=_auth(admin_token))
    assert stopped.json()["status"] == "stopped"


def test_incoming_creates_subscriber_and_conversation(client, admin_token, bot):
    r = client.post(
        f"/api/bots/{bot['id']}/simulate-incoming",
        headers=_auth(admin_token),
        json={"telegram_user_id": 500900, "name": "Alice", "text": "hi bot", "utm_source": "instagram"},
    )
    assert r.status_code == 200
    conv = r.json()
    assert conv["unread_count"] == 1
    assert conv["label"] == "Alice"

    # Subscriber captured with UTM.
    subs = client.get(f"/api/bots/{bot['id']}/subscribers", headers=_auth(admin_token)).json()
    assert any(s["telegram_user_id"] == 500900 and s["utm_source"] == "instagram" for s in subs)

    # Thread has the incoming message.
    thread = client.get(
        f"/api/bots/{bot['id']}/conversations/{conv['id']}", headers=_auth(admin_token)
    ).json()
    assert thread["messages"][0]["direction"] == "in"
    assert thread["messages"][0]["body"] == "hi bot"

    # Counts reflect the subscriber.
    detail = client.get(f"/api/bots/{bot['id']}", headers=_auth(admin_token)).json()
    assert detail["counts"]["started"] == 1


def test_reply_sends_via_bot(client, admin_token, bot, monkeypatch):
    conv = client.post(
        f"/api/bots/{bot['id']}/simulate-incoming", headers=_auth(admin_token),
        json={"telegram_user_id": 500901, "name": "Bob", "text": "question?"},
    ).json()

    sent = []

    async def _send(bot_id, token, chat_id, text):
        sent.append((chat_id, text))
        return {"sent": True, "tg_message_id": 1}

    monkeypatch.setattr(engine_client, "bot_send", _send)
    r = client.post(
        f"/api/bots/{bot['id']}/conversations/{conv['id']}/reply",
        headers=_auth(admin_token), json={"text": "here's the answer"},
    )
    assert r.status_code == 200
    assert r.json()["direction"] == "out"
    assert sent and sent[0] == (500901, "here's the answer")


def test_broadcast(client, admin_token, bot, monkeypatch):
    for uid in (500910, 500911):
        client.post(
            f"/api/bots/{bot['id']}/simulate-incoming", headers=_auth(admin_token),
            json={"telegram_user_id": uid, "text": "hey"},
        )

    async def _send(bot_id, token, chat_id, text):
        return {"sent": True}

    monkeypatch.setattr(engine_client, "bot_send", _send)
    r = client.post(f"/api/bots/{bot['id']}/broadcast", headers=_auth(admin_token), json={"text": "news!"})
    assert r.status_code == 200
    assert r.json()["sent"] == 2


def test_post_to_channel(client, admin_token, bot, monkeypatch):
    async def _post(bot_id, token, chat_id, text, image_url):
        return {"sent": True, "tg_message_id": 9}

    monkeypatch.setattr(engine_client, "bot_post", _post)
    r = client.post(
        f"/api/bots/{bot['id']}/post", headers=_auth(admin_token),
        json={"chat_id": "@mychannel", "text": "New drop!", "image_url": "https://x/i.jpg"},
    )
    assert r.status_code == 200
    assert r.json()["sent"] is True


def test_deep_link(client, admin_token, bot):
    r = client.get(f"/api/bots/{bot['id']}/deep-link?utm=facebook", headers=_auth(admin_token))
    assert r.json()["deep_link"] == "https://t.me/demo_bot?start=facebook"


def test_websocket_receives_bot_message(client, admin_token, bot):
    with client.websocket_connect(f"/ws/inbox?token={admin_token}") as ws:
        assert ws.receive_json()["type"] == "connected"
        client.post(
            f"/api/bots/{bot['id']}/simulate-incoming", headers=_auth(admin_token),
            json={"telegram_user_id": 500920, "name": "Live", "text": "live bot msg"},
        )
        event = ws.receive_json()
        assert event["type"] == "bot_message"
        assert event["message"]["body"] == "live bot msg"


def test_agent_cannot_access_bots(client, admin_token):
    client.post(
        "/api/users", headers=_auth(admin_token),
        json={"email": "agent10@test.com", "password": "AgentPass123", "role": "agent"},
    )
    agent = _login(client, "agent10@test.com", "AgentPass123")
    assert client.get("/api/bots", headers=_auth(agent)).status_code == 403
