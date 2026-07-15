"""Phase 9 acceptance: campaigns + drip + A/B (segments, variants, scheduling)."""

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


def _logged_in_account(client, token, monkeypatch, label="Camp Acc") -> int:
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


def _mk_template(client, token, group, label, body="Hi {there|hey}"):
    r = client.post(
        "/api/templates", headers=_auth(token),
        json={"name": f"{group}-{label}", "body": body, "variant_group": group, "variant_label": label},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _mk_contact(client, token, username, source):
    return client.post(
        "/api/contacts", headers=_auth(token),
        json={"username": username, "consent": True, "source": source},
    ).json()


# ---------------------------------------------------------------- templates ---


def test_template_ab_variants(client, admin_token):
    _mk_template(client, admin_token, "grp_ab9", "A")
    _mk_template(client, admin_token, "grp_ab9", "B")
    templates = client.get("/api/templates", headers=_auth(admin_token)).json()
    group = [t for t in templates if t["variant_group"] == "grp_ab9"]
    assert len(group) == 2
    assert {t["variant_label"] for t in group} == {"A", "B"}


# ---------------------------------------------------- segment / materialize ---


def test_ab_materialize_splits_variants(client, admin_token):
    _mk_template(client, admin_token, "vg_split9", "A")
    _mk_template(client, admin_token, "vg_split9", "B")
    for u in ("s1", "s2", "s3", "s4"):
        _mk_contact(client, admin_token, f"@{u}_p9ab", "p9ab")

    camp = client.post(
        "/api/campaigns", headers=_auth(admin_token),
        json={
            "name": "AB", "action": "message", "segment": {"source": "p9ab"},
            "steps": [{"offset_hours": 0, "variant_group": "vg_split9"}], "ab_test": True,
        },
    ).json()
    detail = client.post(
        f"/api/campaigns/{camp['id']}/start", headers=_auth(admin_token)
    ).json()
    assert detail["stats"]["queued"] == 4
    template_ids = {t["template_id"] for t in detail["targets"]}
    assert len(template_ids) == 2  # both A/B variants assigned


def test_drip_schedules_multiple_steps(client, admin_token):
    _mk_template(client, admin_token, "vg_drip9", "A")
    _mk_contact(client, admin_token, "@drip_p9", "p9drip")
    camp = client.post(
        "/api/campaigns", headers=_auth(admin_token),
        json={
            "name": "Drip", "action": "message", "segment": {"source": "p9drip"},
            "steps": [
                {"offset_hours": 0, "variant_group": "vg_drip9"},
                {"offset_hours": 24, "variant_group": "vg_drip9"},
            ],
        },
    ).json()
    detail = client.post(
        f"/api/campaigns/{camp['id']}/start", headers=_auth(admin_token)
    ).json()
    assert detail["stats"]["queued"] == 2  # one contact, two drip steps
    assert sorted(t["step"] for t in detail["targets"]) == [0, 1]


def test_segment_excludes_already_in_destination(client, admin_token, monkeypatch):
    aid = _logged_in_account(client, admin_token, monkeypatch)
    _isolate_via_api(client, admin_token, aid)

    async def _resolve(a, p, link):
        return {"tg_entity_id": 810001, "title": "X", "type": "group"}

    monkeypatch.setattr(engine_client, "resolve_destination", _resolve)
    dest = client.post(
        "/api/destinations", headers=_auth(admin_token), json={"link": "https://t.me/excl9"}
    ).json()

    inside = _mk_contact(client, admin_token, "@excl_in_p9", "p9excl")
    outside = _mk_contact(client, admin_token, "@excl_out_p9", "p9excl")
    client.post(
        f"/api/destinations/{dest['id']}/add-members", headers=_auth(admin_token),
        json={"contact_ids": [inside["id"]]},
    )

    async def _add(a, p, e, t):
        return {"state": "added", "method": "direct_add"}

    monkeypatch.setattr(engine_client, "add_member", _add)
    client.post(f"/api/destinations/{dest['id']}/add-members/tick", headers=_auth(admin_token))

    _mk_template(client, admin_token, "vg_excl9", "A")
    camp = client.post(
        "/api/campaigns", headers=_auth(admin_token),
        json={
            "name": "Excl", "action": "message",
            "segment": {"source": "p9excl", "exclude_in_destination": dest["id"]},
            "steps": [{"offset_hours": 0, "variant_group": "vg_excl9"}],
        },
    ).json()
    detail = client.post(
        f"/api/campaigns/{camp['id']}/start", headers=_auth(admin_token)
    ).json()
    contact_ids = {t["contact_id"] for t in detail["targets"]}
    assert outside["id"] in contact_ids
    assert inside["id"] not in contact_ids  # already in the destination -> excluded


# --------------------------------------------------------------------- tick ---


def test_message_campaign_tick_sends_and_reports(client, admin_token, monkeypatch):
    aid = _logged_in_account(client, admin_token, monkeypatch, label="Msg Camp")
    _isolate_via_api(client, admin_token, aid)
    _mk_template(client, admin_token, "vg_send9", "A", body="Hello {there|hi}!")
    contact = _mk_contact(client, admin_token, "@send_p9", "p9send")
    camp = client.post(
        "/api/campaigns", headers=_auth(admin_token),
        json={
            "name": "Send", "action": "message", "segment": {"source": "p9send"},
            "steps": [{"offset_hours": 0, "variant_group": "vg_send9"}],
        },
    ).json()
    client.post(f"/api/campaigns/{camp['id']}/start", headers=_auth(admin_token))

    sent = []

    async def _send(account, proxy, target, text):
        sent.append(text)
        return {"sent": True}

    monkeypatch.setattr(engine_client, "send_message", _send)
    tick = client.post(f"/api/campaigns/{camp['id']}/tick", headers=_auth(admin_token))
    assert tick.json()["sent"] == 1
    assert sent and "{" not in sent[0]

    # Landed in the inbox.
    convs = client.get("/api/inbox/conversations", headers=_auth(admin_token)).json()
    assert any(c["contact_id"] == contact["id"] for c in convs)

    # A/B report reflects the send.
    detail = client.get(f"/api/campaigns/{camp['id']}", headers=_auth(admin_token)).json()
    assert detail["stats"]["sent"] == 1
    assert any(r["sent"] == 1 for r in detail["ab_report"])


def test_add_campaign_tick_creates_membership(client, admin_token, monkeypatch):
    aid = _logged_in_account(client, admin_token, monkeypatch, label="Add Camp")
    _isolate_via_api(client, admin_token, aid)

    async def _resolve(a, p, link):
        return {"tg_entity_id": 820001, "title": "G", "type": "group"}

    monkeypatch.setattr(engine_client, "resolve_destination", _resolve)
    dest = client.post(
        "/api/destinations", headers=_auth(admin_token), json={"link": "https://t.me/addcamp9"}
    ).json()
    _mk_contact(client, admin_token, "@addcamp_p9", "p9addcamp")

    camp = client.post(
        "/api/campaigns", headers=_auth(admin_token),
        json={
            "name": "AddCamp", "action": "add", "destination_id": dest["id"],
            "segment": {"source": "p9addcamp"}, "steps": [{"offset_hours": 0}],
        },
    ).json()
    client.post(f"/api/campaigns/{camp['id']}/start", headers=_auth(admin_token))

    async def _add(a, p, e, t):
        return {"state": "added", "method": "direct_add"}

    monkeypatch.setattr(engine_client, "add_member", _add)
    tick = client.post(f"/api/campaigns/{camp['id']}/tick", headers=_auth(admin_token))
    assert tick.json()["joined"] == 1

    ddetail = client.get(f"/api/destinations/{dest['id']}", headers=_auth(admin_token)).json()
    assert ddetail["stats"]["added"] == 1


def test_campaign_tick_flood_pauses(client, admin_token, monkeypatch):
    aid = _logged_in_account(client, admin_token, monkeypatch, label="Flood Camp")
    _isolate_via_api(client, admin_token, aid)
    _mk_template(client, admin_token, "vg_flood9", "A")
    _mk_contact(client, admin_token, "@floodcamp_p9", "p9floodcamp")
    camp = client.post(
        "/api/campaigns", headers=_auth(admin_token),
        json={
            "name": "Flood", "action": "message", "segment": {"source": "p9floodcamp"},
            "steps": [{"offset_hours": 0, "variant_group": "vg_flood9"}],
        },
    ).json()
    client.post(f"/api/campaigns/{camp['id']}/start", headers=_auth(admin_token))

    async def _flood(account, proxy, target, text):
        return {"sent": False, "error": "peerflood"}

    monkeypatch.setattr(engine_client, "send_message", _flood)
    tick = client.post(f"/api/campaigns/{camp['id']}/tick", headers=_auth(admin_token))
    assert tick.json()["paused"] is True
    camp2 = client.get(f"/api/campaigns/{camp['id']}", headers=_auth(admin_token)).json()
    assert camp2["status"] == "paused"


def test_message_campaign_requires_variant_group(client, admin_token):
    r = client.post(
        "/api/campaigns", headers=_auth(admin_token),
        json={
            "name": "Bad", "action": "message", "segment": {},
            "steps": [{"offset_hours": 0}],  # no variant_group
        },
    )
    assert r.status_code == 400


def test_agent_cannot_access_campaigns(client, admin_token):
    client.post(
        "/api/users", headers=_auth(admin_token),
        json={"email": "agent9@test.com", "password": "AgentPass123", "role": "agent"},
    )
    agent = _login(client, "agent9@test.com", "AgentPass123")
    assert client.get("/api/campaigns", headers=_auth(agent)).status_code == 403
    assert client.get("/api/templates", headers=_auth(agent)).status_code == 403
