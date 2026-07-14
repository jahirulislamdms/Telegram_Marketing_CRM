"""Phase 4 acceptance: warmup runs, staged ramp, and paced fleet/partner actions.

Stage advancement is tested against a simulated clock; Telegram side effects are
delegated through an injected executor (engine mocked).
"""

from datetime import timedelta

import pytest

from app.db.models.account import Account
from app.services import engine_client
from app.services import warmup as ws
from app.services.warmup import _as_utc
from tests.conftest import TestSessionLocal


async def _mk_account(db, label, phone=None) -> Account:
    account = Account(label=label, phone=phone, status="logged_out", session_ref="1")
    db.add(account)
    await db.commit()
    await db.refresh(account)
    return account


# ------------------------------------------------------- pure/service logic ---


async def test_stage_advances_on_schedule():
    async with TestSessionLocal() as db:
        account = await _mk_account(db, "warm-stage")
        run = await ws.create_run(
            db,
            name="Ramp",
            groups=[],
            messages=[],
            stages=[{"days": 3, "max_actions": 2}, {"days": 4, "max_actions": 5}],
            min_delay_seconds=40,
            max_delay_seconds=180,
            created_by=None,
        )
        await ws.add_participants(db, run, [account.id])
        await ws.start_run(db, run)

        p = (await ws.get_participants(db, run.id))[0]
        assert p.stage == 0
        base = _as_utc(p.stage_started_at)

        async def noop(participant, acc, action):
            return None

        # +1 day: still stage 0.
        await ws.run_tick(db, run, base + timedelta(days=1), noop)
        p = (await ws.get_participants(db, run.id))[0]
        assert p.stage == 0

        # +3 days: advances to stage 1.
        await ws.run_tick(db, run, base + timedelta(days=3, seconds=1), noop)
        p = (await ws.get_participants(db, run.id))[0]
        assert p.stage == 1
        account = await db.get(Account, account.id)
        assert account.warmup_stage == 1


async def test_final_stage_completes_and_reactivates_account():
    async with TestSessionLocal() as db:
        account = await _mk_account(db, "warm-complete")
        run = await ws.create_run(
            db,
            name="Short",
            groups=[],
            messages=[],
            stages=[{"days": 1, "max_actions": 2}],
            min_delay_seconds=40,
            max_delay_seconds=180,
            created_by=None,
        )
        await ws.add_participants(db, run, [account.id])
        await ws.start_run(db, run)
        p = (await ws.get_participants(db, run.id))[0]
        base = _as_utc(p.stage_started_at)

        async def noop(participant, acc, action):
            return None

        summary = await ws.run_tick(db, run, base + timedelta(days=1, seconds=1), noop)
        assert summary["completed"] == 1
        p = (await ws.get_participants(db, run.id))[0]
        assert p.status == "done"
        account = await db.get(Account, account.id)
        assert account.status == "active"


async def test_tick_joins_then_chit_chats():
    async with TestSessionLocal() as db:
        a1 = await _mk_account(db, "peerA", phone="+15550000001")
        a2 = await _mk_account(db, "peerB", phone="+15550000002")
        run = await ws.create_run(
            db,
            name="Chat",
            groups=["https://t.me/somegroup"],
            messages=["hi", "yo"],
            stages=[{"days": 10, "max_actions": 5}],
            min_delay_seconds=40,
            max_delay_seconds=180,
            created_by=None,
        )
        await ws.add_participants(db, run, [a1.id, a2.id])
        await ws.add_partner(db, run, "@partner1", "username")
        await ws.start_run(db, run)
        base = _as_utc((await ws.get_participants(db, run.id))[0].stage_started_at)

        calls = []

        async def record(participant, account, action):
            calls.append((account.id, action["type"]))

        # First tick: both accounts join the group.
        s1 = await ws.run_tick(db, run, base, record)
        assert len(s1["actions"]) == 2
        assert all(a["type"] == "join" for a in s1["actions"])

        # Second tick after the delay: groups joined -> chit-chat send.
        s2 = await ws.run_tick(db, run, base + timedelta(seconds=60), record)
        assert len(s2["actions"]) == 2
        assert all(a["type"] == "send" for a in s2["actions"])


async def test_daily_cap_limits_actions():
    async with TestSessionLocal() as db:
        account = await _mk_account(db, "capped", phone="+15550000009")
        run = await ws.create_run(
            db,
            name="Cap",
            groups=["https://t.me/g1", "https://t.me/g2", "https://t.me/g3"],
            messages=["hi"],
            stages=[{"days": 10, "max_actions": 1}],  # 1 action/day
            min_delay_seconds=1,
            max_delay_seconds=5,
            created_by=None,
        )
        await ws.add_participants(db, run, [account.id])
        await ws.start_run(db, run)
        base = _as_utc((await ws.get_participants(db, run.id))[0].stage_started_at)

        async def noop(participant, acc, action):
            return None

        await ws.run_tick(db, run, base, noop)
        # Second action same day exceeds the cap of 1.
        s2 = await ws.run_tick(db, run, base + timedelta(seconds=10), noop)
        assert len(s2["actions"]) == 0
        p = (await ws.get_participants(db, run.id))[0]
        assert p.actions_today == 1


# ------------------------------------------------------------------ API/RBAC --


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _login(client, email, password) -> str:
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture()
def admin_token(client, admin_credentials) -> str:
    return _login(client, **admin_credentials)


def test_warmup_workflow_via_api(client, admin_token, monkeypatch):
    # Create two accounts to warm.
    ids = []
    for label in ("W-API-1", "W-API-2"):
        r = client.post(
            "/api/accounts",
            headers=_auth(admin_token),
            json={"label": label, "assign_proxy": False},
        )
        ids.append(r.json()["id"])

    run = client.post(
        "/api/warmup/runs",
        headers=_auth(admin_token),
        json={
            "name": "Campaign A",
            "groups": ["https://t.me/mygroup"],
            "messages": ["hey", "hello"],
        },
    )
    assert run.status_code == 201
    run_id = run.json()["id"]
    # Default stages applied.
    assert len(run.json()["stages"]) == 3

    client.post(
        f"/api/warmup/runs/{run_id}/participants",
        headers=_auth(admin_token),
        json={"account_ids": ids},
    )
    detail = client.post(
        f"/api/warmup/runs/{run_id}/partners",
        headers=_auth(admin_token),
        json={"identifier": "@buddy", "kind": "username"},
    )
    assert len(detail.json()["participants"]) == 2
    assert len(detail.json()["partners"]) == 1
    assert detail.json()["participants"][0]["stage_progress"] == "1/3"

    started = client.post(
        f"/api/warmup/runs/{run_id}/start", headers=_auth(admin_token)
    )
    assert started.json()["status"] == "running"

    joins = []

    async def fake_join(account, proxy, link):
        joins.append((account.id, link))
        return {"joined": True}

    monkeypatch.setattr(engine_client, "warmup_join", fake_join)

    tick = client.post(f"/api/warmup/runs/{run_id}/tick", headers=_auth(admin_token))
    assert tick.status_code == 200
    assert len(tick.json()["actions"]) == 2
    assert len(joins) == 2

    paused = client.post(f"/api/warmup/runs/{run_id}/pause", headers=_auth(admin_token))
    assert paused.json()["status"] == "paused"
    # Tick is rejected when not running.
    assert (
        client.post(f"/api/warmup/runs/{run_id}/tick", headers=_auth(admin_token)).status_code
        == 400
    )

    stopped = client.post(f"/api/warmup/runs/{run_id}/stop", headers=_auth(admin_token))
    assert stopped.json()["status"] == "done"


def test_agent_cannot_access_warmup(client, admin_token):
    client.post(
        "/api/users",
        headers=_auth(admin_token),
        json={"email": "agent4@test.com", "password": "AgentPass123", "role": "agent"},
    )
    agent_token = _login(client, "agent4@test.com", "AgentPass123")
    assert client.get("/api/warmup/runs", headers=_auth(agent_token)).status_code == 403
