"""Phase 7 acceptance: sender engine + anti-ban (rotation, caps, spintax, autopause)."""

import random
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import update

from app.db.models.account import Account
from app.db.models.contact import Contact
from app.db.models.sender import SendJob
from app.services import engine_client
from app.services import sender as ss
from app.services.sender import render_message
from tests.conftest import TestSessionLocal
from worker.antiban import pacing
from worker.antiban.spintax import spin


async def _isolate_accounts(db) -> None:
    """Make every pre-existing account ineligible so tests control the pool."""
    await db.execute(update(Account).values(session_ref=None, status="logged_out"))
    await db.commit()


# ------------------------------------------------------------------ pure -----


def test_spin_picks_one_variant():
    out = spin("Hi {there|hello|hey}!", random.Random(3))
    assert "{" not in out and "}" not in out
    assert out.startswith("Hi ") and out.endswith("!")


def test_spin_nested():
    out = spin("{A{1|2}|B}", random.Random(0))
    assert out in ("A1", "A2", "B")


def test_rotate():
    assert pacing.rotate([1, 2, 3], None) == [1, 2, 3]
    assert pacing.rotate([1, 2, 3], 1) == [2, 3, 1]
    assert pacing.rotate([1, 2, 3], 2) == [3, 1, 2]
    assert pacing.rotate([5], 5) == [5]
    assert pacing.rotate([], None) == []


def test_under_daily_cap():
    assert pacing.under_daily_cap(0, 30)
    assert not pacing.under_daily_cap(30, 30)


def test_delay_ok():
    now = datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc)
    assert pacing.delay_ok(None, now, 40)
    assert not pacing.delay_ok(now - timedelta(seconds=10), now, 40)
    assert pacing.delay_ok(now - timedelta(seconds=60), now, 40)


def test_in_window():
    day = datetime(2026, 7, 14, 10, 0, tzinfo=timezone.utc)
    assert pacing.in_window(day, "09:00", "21:00")
    night = datetime(2026, 7, 14, 22, 0, tzinfo=timezone.utc)
    assert not pacing.in_window(night, "09:00", "21:00")
    # Overnight window.
    assert pacing.in_window(night, "21:00", "06:00")


def test_render_suppresses_link_on_first_contact():
    job = SendJob(
        name="j", template="Hi", include_link=True, link_url="http://x.io",
        suppress_link_first=True,
    )
    first = Contact(name="a", lead_type="username", username="u")
    first.last_contacted_at = None
    assert "http://x.io" not in render_message(job, first, random.Random(0))

    later = Contact(name="b", lead_type="username", username="u2")
    later.last_contacted_at = datetime.now(timezone.utc)
    assert "http://x.io" in render_message(job, later, random.Random(0))


# ------------------------------------------------------- service (rotation) --


async def _mk_account(db, label, ref, actions_today=0, daily_cap=30) -> Account:
    account = Account(
        label=label, session_ref=ref, status="active",
        actions_today=actions_today, daily_cap=daily_cap,
    )
    db.add(account)
    await db.commit()
    await db.refresh(account)
    return account


async def _mk_contact(db, username) -> Contact:
    contact = Contact(
        lead_type="username", username=username, consent=True, tags=[], utm={}
    )
    db.add(contact)
    await db.commit()
    await db.refresh(contact)
    return contact


async def test_tick_rotates_across_accounts():
    async with TestSessionLocal() as db:
        await _isolate_accounts(db)
        a1 = await _mk_account(db, "rot-a", "ra")
        a2 = await _mk_account(db, "rot-b", "rb")
        job = await ss.create_job(
            db, name="Rot", template="hi", include_link=False, link_url=None,
            suppress_link_first=True, created_by=None,
        )
        await ss.start_job(db, job)
        c1 = await _mk_contact(db, "rot1")
        c2 = await _mk_contact(db, "rot2")
        await ss.add_targets(db, job, contact_ids=[c1.id, c2.id])

        used = []

        async def fake(account, contact, body):
            used.append(account.id)
            return {"ok": True}

        summary = await ss.run_tick(db, job, datetime.now(timezone.utc), fake, min_delay=40)
        assert summary["sent"] == 2
        assert set(used) == {a1.id, a2.id}  # both accounts used (rotation)


async def test_tick_respects_daily_cap():
    async with TestSessionLocal() as db:
        await _isolate_accounts(db)
        under = await _mk_account(db, "cap-under", "cu", actions_today=0)
        await _mk_account(db, "cap-at", "ca", actions_today=30, daily_cap=30)
        job = await ss.create_job(
            db, name="Cap", template="hi", include_link=False, link_url=None,
            suppress_link_first=True, created_by=None,
        )
        await ss.start_job(db, job)
        c1 = await _mk_contact(db, "cap1")
        c2 = await _mk_contact(db, "cap2")
        await ss.add_targets(db, job, contact_ids=[c1.id, c2.id])

        used = []

        async def fake(account, contact, body):
            used.append(account.id)
            return {"ok": True}

        summary = await ss.run_tick(db, job, datetime.now(timezone.utc), fake, min_delay=40)
        # Only the under-cap account sends (one send per usable account per tick).
        assert summary["sent"] == 1
        assert used == [under.id]


# ----------------------------------------------------------------- API -------


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _login(client, email, password) -> str:
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture()
def admin_token(client, admin_credentials) -> str:
    return _login(client, **admin_credentials)


def _logged_in_account(client, token, monkeypatch, label="Sender Acc") -> int:
    created = client.post(
        "/api/accounts", headers=_auth(token), json={"label": label, "assign_proxy": False}
    )
    aid = created.json()["id"]

    async def _qr(_id):
        return {"status": "authorized", "url": None, "user": {"id": 7}, "detail": None}

    monkeypatch.setattr(engine_client, "qr_status", _qr)
    client.get(f"/api/accounts/{aid}/login/qr", headers=_auth(token))
    return aid


def test_targets_only_consented(client, admin_token):
    def _mk(username, consent, opt=False):
        c = client.post(
            "/api/contacts", headers=_auth(admin_token),
            json={"username": username, "consent": consent},
        ).json()
        if opt:
            client.patch(
                f"/api/contacts/{c['id']}", headers=_auth(admin_token),
                json={"stage": "opted_out"},
            )
        return c["id"]

    ok = _mk("@p7ok", True)
    no_consent = _mk("@p7noc", False)
    opted = _mk("@p7opt", True, opt=True)

    job = client.post(
        "/api/sender/jobs", headers=_auth(admin_token),
        json={"name": "Filter", "template": "hi"},
    ).json()
    detail = client.post(
        f"/api/sender/jobs/{job['id']}/targets", headers=_auth(admin_token),
        json={"contact_ids": [ok, no_consent, opted]},
    ).json()
    assert detail["stats"]["queued"] == 1  # only the consented, non-opted contact


def test_send_lands_in_inbox_and_advances_stage(client, admin_token, monkeypatch):
    _logged_in_account(client, admin_token, monkeypatch)
    contact = client.post(
        "/api/contacts", headers=_auth(admin_token),
        json={"username": "@p7lead", "consent": True},
    ).json()
    job = client.post(
        "/api/sender/jobs", headers=_auth(admin_token),
        json={"name": "Blast", "template": "Hello {there|hi}!"},
    ).json()
    client.post(
        f"/api/sender/jobs/{job['id']}/targets", headers=_auth(admin_token),
        json={"contact_ids": [contact["id"]]},
    )
    client.post(f"/api/sender/jobs/{job['id']}/start", headers=_auth(admin_token))

    sent = []

    async def _send(account, proxy, target, text):
        sent.append((target, text))
        return {"sent": True}

    monkeypatch.setattr(engine_client, "send_message", _send)
    tick = client.post(f"/api/sender/jobs/{job['id']}/tick", headers=_auth(admin_token))
    assert tick.status_code == 200
    assert tick.json()["sent"] == 1
    assert sent and "{" not in sent[0][1]  # spintax rendered

    # Landed in the inbox.
    convs = client.get("/api/inbox/conversations", headers=_auth(admin_token)).json()
    assert any(c["contact_id"] == contact["id"] for c in convs)

    # Target marked sent, contact advanced to contacted.
    detail = client.get(f"/api/sender/jobs/{job['id']}", headers=_auth(admin_token)).json()
    assert detail["stats"]["sent"] == 1
    refreshed = client.get(
        f"/api/contacts/{contact['id']}", headers=_auth(admin_token)
    ).json()
    assert refreshed["stage"] == "contacted"


def _isolate_via_api(client, token, keep_id):
    for a in client.get("/api/accounts", headers=_auth(token)).json():
        if a["id"] != keep_id and a["session_ref"] and a["status"] == "active":
            client.patch(
                f"/api/accounts/{a['id']}/status",
                headers=_auth(token),
                json={"status": "logged_out"},
            )


def test_autopause_on_flood(client, admin_token, monkeypatch):
    aid = _logged_in_account(client, admin_token, monkeypatch, label="Flood Acc")
    _isolate_via_api(client, admin_token, aid)
    contact = client.post(
        "/api/contacts", headers=_auth(admin_token),
        json={"username": "@p7flood", "consent": True},
    ).json()
    job = client.post(
        "/api/sender/jobs", headers=_auth(admin_token),
        json={"name": "Flood", "template": "hi"},
    ).json()
    client.post(
        f"/api/sender/jobs/{job['id']}/targets", headers=_auth(admin_token),
        json={"contact_ids": [contact["id"]]},
    )
    client.post(f"/api/sender/jobs/{job['id']}/start", headers=_auth(admin_token))

    async def _flood(account, proxy, target, text):
        return {"sent": False, "error": "peerflood"}

    monkeypatch.setattr(engine_client, "send_message", _flood)
    tick = client.post(f"/api/sender/jobs/{job['id']}/tick", headers=_auth(admin_token))
    assert tick.json()["paused"] is True

    job_after = client.get(f"/api/sender/jobs/{job['id']}", headers=_auth(admin_token)).json()
    assert job_after["status"] == "paused"
    account = client.get(f"/api/accounts/{aid}", headers=_auth(admin_token)).json()
    assert account["status"] == "quarantined"


def test_tick_requires_running(client, admin_token):
    job = client.post(
        "/api/sender/jobs", headers=_auth(admin_token),
        json={"name": "Draft", "template": "hi"},
    ).json()
    r = client.post(f"/api/sender/jobs/{job['id']}/tick", headers=_auth(admin_token))
    assert r.status_code == 400


def test_agent_cannot_access_sender(client, admin_token):
    client.post(
        "/api/users", headers=_auth(admin_token),
        json={"email": "agent7@test.com", "password": "AgentPass123", "role": "agent"},
    )
    agent = _login(client, "agent7@test.com", "AgentPass123")
    assert client.get("/api/sender/jobs", headers=_auth(agent)).status_code == 403
