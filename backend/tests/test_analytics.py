"""Phase 11 acceptance: dashboard, marketing analytics, and referral program."""

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


def _logged_in_account(client, token, monkeypatch, label="Analytics Acc") -> int:
    created = client.post(
        "/api/accounts", headers=_auth(token), json={"label": label, "assign_proxy": False}
    )
    aid = created.json()["id"]

    async def _qr(_id):
        return {"status": "authorized", "url": None, "user": {"id": 11}, "detail": None}

    monkeypatch.setattr(engine_client, "qr_status", _qr)
    client.get(f"/api/accounts/{aid}/login/qr", headers=_auth(token))
    return aid


def _mk_contact(client, token, username, source, stage=None):
    c = client.post(
        "/api/contacts", headers=_auth(token),
        json={"username": username, "consent": True, "source": source},
    ).json()
    if stage:
        client.post(
            "/api/contacts/bulk/stage", headers=_auth(token),
            json={"contact_ids": [c["id"]], "stage": stage},
        )
    return c


def _make_bot(client, token, monkeypatch, bot_token="900:ANALYTICS"):
    async def _info(_token):
        return {"name": "Analytics Bot", "username": "analytics_bot"}

    monkeypatch.setattr(engine_client, "bot_info", _info)
    r = client.post("/api/bots", headers=_auth(token), json={"token": bot_token})
    assert r.status_code == 201, r.text
    return r.json()


# ------------------------------------------------------------- dashboard -----


def test_dashboard_snapshot_shape(client, admin_token):
    r = client.get("/api/analytics/dashboard", headers=_auth(admin_token))
    assert r.status_code == 200, r.text
    snap = r.json()
    for key in ("accounts", "caps", "queue", "proxies", "throughput", "running_campaigns", "recent_events"):
        assert key in snap, key
    assert "total" in snap["accounts"]
    assert isinstance(snap["running_campaigns"], list)


def test_dashboard_counts_logged_in_account(client, admin_token, monkeypatch):
    before = client.get("/api/analytics/dashboard", headers=_auth(admin_token)).json()
    base_active = before["accounts"]["active"]
    _logged_in_account(client, admin_token, monkeypatch)
    after = client.get("/api/analytics/dashboard", headers=_auth(admin_token)).json()
    assert after["accounts"]["active"] >= base_active + 1
    assert after["accounts"]["total"] >= 1


def test_dashboard_broadcast_over_websocket(client, admin_token):
    with client.websocket_connect(f"/ws/inbox?token={admin_token}") as ws:
        assert ws.receive_json()["type"] == "connected"
        r = client.post("/api/analytics/dashboard/broadcast", headers=_auth(admin_token))
        assert r.status_code == 200, r.text
        event = ws.receive_json()
        assert event["type"] == "dashboard"
        assert "accounts" in event["snapshot"]


# ------------------------------------------------------------- analytics -----


def test_funnel_and_per_source_conversion(client, admin_token):
    src = "p11funnel"
    _mk_contact(client, admin_token, "@f_new_p11", src)  # stays 'new'
    _mk_contact(client, admin_token, "@f_contacted_p11", src, stage="contacted")
    _mk_contact(client, admin_token, "@f_replied_p11", src, stage="replied")
    _mk_contact(client, admin_token, "@f_customer_p11", src, stage="customer")

    overview = client.get("/api/analytics", headers=_auth(admin_token)).json()

    # Funnel: reached counts are cumulative up the pipeline.
    reached = overview["funnel"]["reached"]
    # customer (1) sits above replied; our source alone contributes 3 to 'contacted'
    # (contacted, replied, customer) — global totals may be higher from other tests.
    assert reached["customer"] >= 1
    assert reached["contacted"] >= reached["customer"]

    # Per-source row for our unique source.
    row = next(r for r in overview["per_source"] if r["source"] == src)
    assert row["total"] == 4
    assert row["new"] == 1
    assert row["contacted"] == 1
    assert row["replied"] == 1
    assert row["customer"] == 1
    assert row["conversion_pct"] == 25.0  # 1 customer / 4


def test_per_account_health_listed(client, admin_token, monkeypatch):
    aid = _logged_in_account(client, admin_token, monkeypatch, label="Health Acc")
    overview = client.get("/api/analytics", headers=_auth(admin_token)).json()
    row = next(r for r in overview["per_account"] if r["id"] == aid)
    assert row["logged_in"] is True
    assert row["status"] == "active"
    assert "spam_state" in row


def test_utm_attribution_from_bot_subscribers(client, admin_token, monkeypatch):
    b = _make_bot(client, admin_token, monkeypatch, bot_token="901:UTMTOKEN123")
    client.post(
        f"/api/bots/{b['id']}/simulate-incoming", headers=_auth(admin_token),
        json={"telegram_user_id": 611001, "name": "UTM User", "text": "hi", "utm_source": "p11campaign"},
    )
    overview = client.get("/api/analytics", headers=_auth(admin_token)).json()
    row = next(r for r in overview["utm"] if r["utm_source"] == "p11campaign")
    assert row["subscribers"] >= 1


# ------------------------------------------------------------- referrals -----


def _subscriber_id(client, token, bot_id, telegram_user_id, monkeypatch, name="Ref User"):
    client.post(
        f"/api/bots/{bot_id}/simulate-incoming", headers=_auth(token),
        json={"telegram_user_id": telegram_user_id, "name": name, "text": "start"},
    )
    subs = client.get(f"/api/bots/{bot_id}/subscribers", headers=_auth(token)).json()
    return next(s["id"] for s in subs if s["telegram_user_id"] == telegram_user_id)


def test_referral_create_record_reward_leaderboard(client, admin_token, monkeypatch):
    b = _make_bot(client, admin_token, monkeypatch, bot_token="902:REFTOKEN123")
    sub_id = _subscriber_id(client, admin_token, b["id"], 611100, monkeypatch, name="Top Referrer")

    # Create a personal referral link for the subscriber.
    created = client.post(
        "/api/analytics/referrals", headers=_auth(admin_token),
        json={"subscriber_id": sub_id},
    )
    assert created.status_code == 201, created.text
    referral = created.json()
    assert referral["invited_count"] == 0
    assert referral["deep_link"].startswith("https://t.me/")
    assert f"ref_{referral['invite_code']}" in referral["deep_link"]
    code = referral["invite_code"]

    # Creating again is idempotent (same code).
    again = client.post(
        "/api/analytics/referrals", headers=_auth(admin_token),
        json={"subscriber_id": sub_id},
    ).json()
    assert again["invite_code"] == code

    # Record two referrals against the code (prefixed and bare both accepted).
    r1 = client.post(
        "/api/analytics/referrals/record", headers=_auth(admin_token),
        json={"invite_code": f"ref_{code}"},
    )
    assert r1.status_code == 200, r1.text
    assert r1.json()["invited_count"] == 1
    r2 = client.post(
        "/api/analytics/referrals/record", headers=_auth(admin_token),
        json={"invite_code": code},
    )
    assert r2.json()["invited_count"] == 2

    # Leaderboard reflects the invited_count and label.
    board = client.get("/api/analytics/referrals", headers=_auth(admin_token)).json()
    entry = next(x for x in board if x["invite_code"] == code)
    assert entry["invited_count"] == 2
    assert entry["label"] == "Top Referrer"
    assert entry["rewarded"] is False

    # Reward it.
    reward = client.post(
        f"/api/analytics/referrals/{referral['id']}/reward", headers=_auth(admin_token),
        json={"rewarded": True},
    )
    assert reward.status_code == 200, reward.text
    assert reward.json()["rewarded"] is True


def test_record_unknown_invite_code_404(client, admin_token):
    r = client.post(
        "/api/analytics/referrals/record", headers=_auth(admin_token),
        json={"invite_code": "does_not_exist_zzz"},
    )
    assert r.status_code == 404


def test_create_referral_unknown_subscriber_404(client, admin_token):
    r = client.post(
        "/api/analytics/referrals", headers=_auth(admin_token),
        json={"subscriber_id": 99999999},
    )
    assert r.status_code == 404


# ------------------------------------------------------------------ RBAC -----


def test_agent_cannot_access_analytics(client, admin_token):
    client.post(
        "/api/users", headers=_auth(admin_token),
        json={"email": "agent11@test.com", "password": "AgentPass123", "role": "agent"},
    )
    agent = _login(client, "agent11@test.com", "AgentPass123")
    assert client.get("/api/analytics/dashboard", headers=_auth(agent)).status_code == 403
    assert client.get("/api/analytics", headers=_auth(agent)).status_code == 403
    assert client.get("/api/analytics/referrals", headers=_auth(agent)).status_code == 403
