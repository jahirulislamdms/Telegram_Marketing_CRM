"""Phase 15.5 — inbox performance & UX: batched messages/conversations,
in-conversation search, and save-contact with full details (no duplicates)."""

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


# ------------------------------------------------------ message pagination ---


def test_thread_opens_at_latest_12_messages(client, admin_token, monkeypatch):
    aid = _logged_in_account(client, admin_token, monkeypatch, "perf-acct-1")
    peer = 915001
    for i in range(20):
        _simulate(client, admin_token, aid, peer_id=peer, peer_name="Pager", text=f"msg {i:02d}")
    convs = client.get(
        f"/api/inbox/conversations?account_ids={aid}", headers=_auth(admin_token)
    ).json()
    cid = convs[0]["id"]

    thread = client.get(f"/api/inbox/conversations/{cid}", headers=_auth(admin_token)).json()
    msgs = thread["messages"]
    assert len(msgs) == 12                      # only the newest 12 load
    assert thread["has_more"] is True           # older ones remain
    assert msgs[0]["body"] == "msg 08"          # oldest of the batch
    assert msgs[-1]["body"] == "msg 19"         # newest overall -> opens at latest
    # Chronological order (oldest -> newest).
    assert [m["id"] for m in msgs] == sorted(m["id"] for m in msgs)


def test_load_older_messages_pages_back(client, admin_token, monkeypatch):
    aid = _logged_in_account(client, admin_token, monkeypatch, "perf-acct-2")
    peer = 915002
    for i in range(20):
        _simulate(client, admin_token, aid, peer_id=peer, peer_name="Pager2", text=f"m{i:02d}")
    convs = client.get(
        f"/api/inbox/conversations?account_ids={aid}", headers=_auth(admin_token)
    ).json()
    cid = convs[0]["id"]

    first = client.get(f"/api/inbox/conversations/{cid}", headers=_auth(admin_token)).json()
    oldest_id = first["messages"][0]["id"]

    older = client.get(
        f"/api/inbox/conversations/{cid}/messages?limit=5&before_id={oldest_id}",
        headers=_auth(admin_token),
    ).json()
    assert len(older["messages"]) == 5
    assert older["has_more"] is True
    # Everything returned is strictly older than the batch we already had.
    assert all(m["id"] < oldest_id for m in older["messages"])
    assert older["messages"][-1]["body"] == "m07"  # the 5 immediately before m08

    # Page all the way back: no more older messages remain.
    rest = client.get(
        f"/api/inbox/conversations/{cid}/messages?limit=50&before_id={older['messages'][0]['id']}",
        headers=_auth(admin_token),
    ).json()
    assert rest["has_more"] is False
    assert rest["messages"][0]["body"] == "m00"


def test_short_thread_has_no_older_messages(client, admin_token, monkeypatch):
    aid = _logged_in_account(client, admin_token, monkeypatch, "perf-acct-3")
    _simulate(client, admin_token, aid, peer_id=915003, peer_name="Short", text="only one")
    convs = client.get(
        f"/api/inbox/conversations?account_ids={aid}", headers=_auth(admin_token)
    ).json()
    thread = client.get(
        f"/api/inbox/conversations/{convs[0]['id']}", headers=_auth(admin_token)
    ).json()
    assert len(thread["messages"]) == 1
    assert thread["has_more"] is False


# -------------------------------------------------- in-conversation search ---


def test_search_within_conversation(client, admin_token, monkeypatch):
    aid = _logged_in_account(client, admin_token, monkeypatch, "perf-acct-4")
    peer = 915004
    for text in ["hello there", "pricing question", "PRICING follow up", "goodbye"]:
        _simulate(client, admin_token, aid, peer_id=peer, peer_name="Searcher", text=text)
    convs = client.get(
        f"/api/inbox/conversations?account_ids={aid}", headers=_auth(admin_token)
    ).json()
    cid = convs[0]["id"]

    # Partial, case-insensitive match, scoped to this conversation only.
    found = client.get(
        f"/api/inbox/conversations/{cid}/messages?q=pric&limit=50", headers=_auth(admin_token)
    ).json()
    bodies = [m["body"] for m in found["messages"]]
    assert bodies == ["pricing question", "PRICING follow up"]

    # A term that exists in another chat must not leak in.
    other = _logged_in_account(client, admin_token, monkeypatch, "perf-acct-5")
    _simulate(client, admin_token, other, peer_id=915005, peer_name="Other", text="pricing elsewhere")
    again = client.get(
        f"/api/inbox/conversations/{cid}/messages?q=pric&limit=50", headers=_auth(admin_token)
    ).json()
    assert len(again["messages"]) == 2


# --------------------------------------------------- conversation batching ---


def test_conversation_list_batches_with_total_header(client, admin_token, monkeypatch):
    aid = _logged_in_account(client, admin_token, monkeypatch, "perf-acct-6")
    for i in range(5):
        _simulate(client, admin_token, aid, peer_id=916000 + i, peer_name=f"P{i}", text=f"hi {i}")

    r = client.get(
        f"/api/inbox/conversations?account_ids={aid}&limit=2&offset=0", headers=_auth(admin_token)
    )
    assert r.status_code == 200
    assert r.headers["X-Total-Count"] == "5"
    assert len(r.json()) == 2

    # Next batch continues without overlap.
    page2 = client.get(
        f"/api/inbox/conversations?account_ids={aid}&limit=2&offset=2", headers=_auth(admin_token)
    ).json()
    assert len(page2) == 2
    assert {c["id"] for c in r.json()} & {c["id"] for c in page2} == set()

    # No limit still returns everything (existing callers unaffected).
    all_convs = client.get(
        f"/api/inbox/conversations?account_ids={aid}", headers=_auth(admin_token)
    ).json()
    assert len(all_convs) == 5


# ------------------------------------------------ save contact with details ---


def test_save_contact_with_full_details(client, admin_token, monkeypatch):
    aid = _logged_in_account(client, admin_token, monkeypatch, "perf-acct-7")
    _simulate(
        client, admin_token, aid, peer_id=917001, peer_name="Rich Peer",
        peer_username="richpeer155", text="hello",
    )
    convs = client.get(
        f"/api/inbox/conversations?account_ids={aid}", headers=_auth(admin_token)
    ).json()
    cid = convs[0]["id"]

    r = client.post(
        f"/api/inbox/conversations/{cid}/save-contact",
        headers=_auth(admin_token),
        json={
            "name": "Rich Lead",
            "phone": "+15550155001",
            "source": "inbox_manual",
            "stage": "customer",
            "consent": True,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "Rich Lead"
    assert body["phone"] == "+15550155001"
    assert body["username"] == "richpeer155"      # kept from the peer
    assert body["source"] == "inbox_manual"
    assert body["stage"] == "customer"
    assert body["telegram_user_id"] == 917001


def test_save_contact_updates_existing_instead_of_duplicating(client, admin_token, monkeypatch):
    # An existing CRM contact with a phone we will type in the inbox.
    existing = client.post(
        "/api/contacts", headers=_auth(admin_token),
        json={"name": "Already Known", "phone": "+15550155002", "consent": True},
    ).json()

    aid = _logged_in_account(client, admin_token, monkeypatch, "perf-acct-8")
    _simulate(client, admin_token, aid, peer_id=917002, peer_name="Dup Peer", text="hi")
    convs = client.get(
        f"/api/inbox/conversations?account_ids={aid}", headers=_auth(admin_token)
    ).json()
    cid = convs[0]["id"]

    r = client.post(
        f"/api/inbox/conversations/{cid}/save-contact",
        headers=_auth(admin_token),
        json={"phone": "+15550155002", "name": "Renamed Via Inbox"},
    )
    assert r.status_code == 200, r.text
    # Same record updated in place — no duplicate created.
    assert r.json()["id"] == existing["id"]
    assert r.json()["name"] == "Renamed Via Inbox"
    matches = client.get(
        "/api/contacts?q=15550155002", headers=_auth(admin_token)
    ).json()
    assert len(matches) == 1


def test_save_contact_rejects_identifier_owned_by_another_contact(
    client, admin_token, monkeypatch
):
    client.post(
        "/api/contacts", headers=_auth(admin_token),
        json={"username": "@owned155", "consent": True},
    )
    aid = _logged_in_account(client, admin_token, monkeypatch, "perf-acct-9")
    # This peer already resolves to its own contact, so typing someone else's
    # username must conflict rather than silently steal it.
    _simulate(
        client, admin_token, aid, peer_id=917003, peer_name="Conflict Peer",
        peer_username="conflictpeer155", text="hi",
    )
    convs = client.get(
        f"/api/inbox/conversations?account_ids={aid}", headers=_auth(admin_token)
    ).json()
    cid = convs[0]["id"]
    client.post(f"/api/inbox/conversations/{cid}/save-contact", headers=_auth(admin_token), json={})

    # Now the conversation has a contact; a second save is rejected as before.
    again = client.post(
        f"/api/inbox/conversations/{cid}/save-contact", headers=_auth(admin_token), json={}
    )
    assert again.status_code == 400
