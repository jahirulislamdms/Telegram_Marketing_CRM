"""Phase 5 acceptance: contacts import (CSV+Excel), dedupe, resolution, messaging.

The engine is mocked (resolution/messaging need a live authorized account).
"""

import io

import pytest
from openpyxl import Workbook

from app.services import engine_client
from app.services.contacts import (
    normalize_phone,
    normalize_username,
    parse_bool,
    parse_csv,
)


# ------------------------------------------------------------------ pure -----


def test_normalize_phone():
    assert normalize_phone(" +1 (415) 555-0123 ") == "+14155550123"
    assert normalize_phone("") is None
    assert normalize_phone(None) is None


def test_normalize_username():
    assert normalize_username("@Sara_Ali") == "sara_ali"
    assert normalize_username("  Bob ") == "bob"
    assert normalize_username("") is None


def test_parse_bool():
    assert parse_bool("true") and parse_bool("1") and parse_bool("YES")
    assert not parse_bool("false")
    assert not parse_bool("")
    assert not parse_bool(None)


def test_parse_csv():
    data = b"name,phone,username,source,consent\nAhmed,+123,,offline,true\n"
    rows = parse_csv(data)
    assert rows[0]["name"] == "Ahmed"
    assert rows[0]["phone"] == "+123"
    assert rows[0]["consent"] == "true"


# ------------------------------------------------------------------ API ------


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _login(client, email, password) -> str:
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture()
def admin_token(client, admin_credentials) -> str:
    return _login(client, **admin_credentials)


def _logged_in_account(client, token, monkeypatch) -> int:
    created = client.post(
        "/api/accounts",
        headers=_auth(token),
        json={"label": "resolver", "assign_proxy": False},
    )
    aid = created.json()["id"]

    async def _qr(_id):
        return {"status": "authorized", "url": None, "user": {"id": 7}, "detail": None}

    monkeypatch.setattr(engine_client, "qr_status", _qr)
    client.get(f"/api/accounts/{aid}/login/qr", headers=_auth(token))
    return aid


def test_import_csv_dedupe_and_consent(client, admin_token):
    csv_data = (
        "name,phone,username,source,consent\n"
        "Ahmed Khan,+923001234501,,offline_store,true\n"
        "Sara Ali,,@sara_ali_p5,online_store,true\n"
        ",+14155550501,,online_store,true\n"
        "Dup Phone,+923001234501,,x,true\n"
        "No Consent,+923001234502,,x,false\n"
        "Bad Row,,,x,true\n"
    ).encode()
    r = client.post(
        "/api/contacts/import",
        headers=_auth(admin_token),
        files={"file": ("contacts.csv", csv_data, "text/csv")},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["imported"] == 3
    assert body["skipped_duplicates"] == 1
    assert body["rejected_no_consent"] == 1
    assert body["invalid"] == 1


def test_import_excel(client, admin_token):
    wb = Workbook()
    ws = wb.active
    ws.append(["name", "phone", "username", "source", "consent"])
    ws.append(["Excel User", "", "@excel_user_p5", "online", "true"])
    ws.append(["", "+15550009901", "", "online", "true"])
    buf = io.BytesIO()
    wb.save(buf)
    r = client.post(
        "/api/contacts/import",
        headers=_auth(admin_token),
        files={
            "file": (
                "contacts.xlsx",
                buf.getvalue(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["imported"] == 2


def test_import_template_download(client, admin_token):
    r = client.get("/api/contacts/import-template", headers=_auth(admin_token))
    assert r.status_code == 200
    assert "name,phone,username,source,consent" in r.text


def test_create_and_display_label(client, admin_token):
    r = client.post(
        "/api/contacts",
        headers=_auth(admin_token),
        json={"username": "@crud_user_p5", "consent": True, "source": "test"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["lead_type"] == "username"
    assert body["display_label"] == "@crud_user_p5"

    # Stage transitions.
    cid = body["id"]
    p = client.patch(
        f"/api/contacts/{cid}", headers=_auth(admin_token), json={"stage": "contacted"}
    )
    assert p.json()["stage"] == "contacted"
    p2 = client.patch(
        f"/api/contacts/{cid}", headers=_auth(admin_token), json={"stage": "opted_out"}
    )
    assert p2.json()["opted_out"] is True


def test_create_requires_identifier(client, admin_token):
    r = client.post(
        "/api/contacts",
        headers=_auth(admin_token),
        json={"name": "No Identifier", "consent": True},
    )
    assert r.status_code == 422


def test_resolve_username(client, admin_token, monkeypatch):
    _logged_in_account(client, admin_token, monkeypatch)
    contact = client.post(
        "/api/contacts",
        headers=_auth(admin_token),
        json={"username": "@resolvable_p5", "consent": True},
    ).json()

    async def _resolve(account, proxy, username):
        return {"user_id": 123456, "status": "resolved"}

    monkeypatch.setattr(engine_client, "resolve_username", _resolve)
    r = client.post(
        f"/api/contacts/{contact['id']}/resolve", headers=_auth(admin_token)
    )
    assert r.status_code == 200
    assert r.json()["resolution_status"] == "resolved"
    assert r.json()["telegram_user_id"] == 123456


def test_message_updates_stage(client, admin_token, monkeypatch):
    aid = _logged_in_account(client, admin_token, monkeypatch)
    contact = client.post(
        "/api/contacts",
        headers=_auth(admin_token),
        json={"username": "@msg_user_p5", "consent": True},
    ).json()

    sent = []

    async def _send(account, proxy, target, text):
        sent.append((target, text))
        return {"sent": True}

    monkeypatch.setattr(engine_client, "send_message", _send)
    r = client.post(
        f"/api/contacts/{contact['id']}/message",
        headers=_auth(admin_token),
        json={"account_id": aid, "text": "hello there"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["stage"] == "contacted"
    assert r.json()["last_contacted_at"] is not None
    assert sent and sent[0][1] == "hello there"


def test_message_blocked_without_consent(client, admin_token, monkeypatch):
    aid = _logged_in_account(client, admin_token, monkeypatch)
    contact = client.post(
        "/api/contacts",
        headers=_auth(admin_token),
        json={"username": "@noconsent_p5", "consent": False},
    ).json()
    r = client.post(
        f"/api/contacts/{contact['id']}/message",
        headers=_auth(admin_token),
        json={"account_id": aid, "text": "hi"},
    )
    assert r.status_code == 403


def test_message_blocked_when_opted_out(client, admin_token, monkeypatch):
    aid = _logged_in_account(client, admin_token, monkeypatch)
    contact = client.post(
        "/api/contacts",
        headers=_auth(admin_token),
        json={"username": "@optout_p5", "consent": True},
    ).json()
    client.patch(
        f"/api/contacts/{contact['id']}",
        headers=_auth(admin_token),
        json={"stage": "opted_out"},
    )
    r = client.post(
        f"/api/contacts/{contact['id']}/message",
        headers=_auth(admin_token),
        json={"account_id": aid, "text": "hi"},
    )
    assert r.status_code == 403


def test_agent_sees_only_assigned(client, admin_token):
    client.post(
        "/api/users",
        headers=_auth(admin_token),
        json={"email": "agent5@test.com", "password": "AgentPass123", "role": "agent"},
    )
    agent_token = _login(client, "agent5@test.com", "AgentPass123")
    agent_id = client.get("/api/auth/me", headers=_auth(agent_token)).json()["id"]

    owned = client.post(
        "/api/contacts",
        headers=_auth(admin_token),
        json={"username": "@owned_p5", "consent": True},
    ).json()
    client.patch(
        f"/api/contacts/{owned['id']}",
        headers=_auth(admin_token),
        json={"assigned_agent_id": agent_id},
    )
    other = client.post(
        "/api/contacts",
        headers=_auth(admin_token),
        json={"username": "@notowned_p5", "consent": True},
    ).json()

    listing = client.get("/api/contacts", headers=_auth(agent_token)).json()
    ids = {c["id"] for c in listing}
    assert owned["id"] in ids
    assert other["id"] not in ids

    # Agents cannot import or view a contact that isn't theirs.
    assert (
        client.post(
            "/api/contacts/import",
            headers=_auth(agent_token),
            files={"file": ("c.csv", b"name,phone,username,source,consent\n", "text/csv")},
        ).status_code
        == 403
    )
    assert (
        client.get(f"/api/contacts/{other['id']}", headers=_auth(agent_token)).status_code
        == 403
    )
