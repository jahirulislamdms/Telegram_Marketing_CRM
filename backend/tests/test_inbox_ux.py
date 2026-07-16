"""Phase 15.1.d/e/f/g — inbox UX: multi-account filter, search, peer panel, save-as-contact."""

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


# ------------------------------------------- 15.1.e / 15.1.f: account filter --


def test_account_filter_and_account_label(client, admin_token, monkeypatch):
    a1 = _logged_in_account(client, admin_token, monkeypatch, "UX Acct One")
    a2 = _logged_in_account(client, admin_token, monkeypatch, "UX Acct Two")
    c1 = _simulate(client, admin_token, a1, peer_id=810001, peer_name="Peer One", text="hi one").json()
    c2 = _simulate(client, admin_token, a2, peer_id=810002, peer_name="Peer Two", text="hi two").json()

    # 15.1.f — the conversation knows which account owns it.
    assert c1["account_label"] == "UX Acct One"
    assert c2["account_label"] == "UX Acct Two"

    # One account.
    only1 = client.get(
        f"/api/inbox/conversations?account_ids={a1}", headers=_auth(admin_token)
    ).json()
    ids = {c["id"] for c in only1}
    assert c1["id"] in ids and c2["id"] not in ids
    assert all(c["account_id"] == a1 for c in only1)

    # Many accounts.
    both = client.get(
        f"/api/inbox/conversations?account_ids={a1},{a2}", headers=_auth(admin_token)
    ).json()
    ids = {c["id"] for c in both}
    assert c1["id"] in ids and c2["id"] in ids


def test_account_ids_must_be_integers(client, admin_token):
    r = client.get("/api/inbox/conversations?account_ids=abc", headers=_auth(admin_token))
    assert r.status_code == 400


# -------------------------------------------------- 15.1.g: conversation search


def test_conversation_search_within_selection(client, admin_token, monkeypatch):
    aid = _logged_in_account(client, admin_token, monkeypatch, "UX Search Acct")
    _simulate(client, admin_token, aid, peer_id=810010, peer_name="Zebra Zenith", text="alpha msg")
    _simulate(client, admin_token, aid, peer_id=810011, peer_name="Quokka Quill", text="beta msg")

    # By peer name.
    res = client.get(
        f"/api/inbox/conversations?account_ids={aid}&q=zebra", headers=_auth(admin_token)
    ).json()
    assert len(res) == 1 and res[0]["label"] == "Zebra Zenith"

    # By last-message preview.
    res = client.get(
        f"/api/inbox/conversations?account_ids={aid}&q=beta", headers=_auth(admin_token)
    ).json()
    assert len(res) == 1 and res[0]["label"] == "Quokka Quill"


# ------------------------------------ 15.1.d: peer details + save-as-contact --


def test_peer_username_stored_normalised(client, admin_token, monkeypatch):
    aid = _logged_in_account(client, admin_token, monkeypatch, "UX User Acct")
    conv = _simulate(
        client, admin_token, aid,
        peer_id=810020, peer_name="Named Peer", peer_username="@SomeUser", text="hi",
    ).json()
    assert conv["peer_username"] == "someuser"  # '@' stripped, lowercased


def test_save_peer_as_contact(client, admin_token, monkeypatch):
    aid = _logged_in_account(client, admin_token, monkeypatch, "UX Save Acct")
    conv = _simulate(
        client, admin_token, aid,
        peer_id=810030, peer_name="Unsaved Pal", peer_username="unsavedpal", text="hello!",
    ).json()
    assert conv["contact_id"] is None  # unlinked peer

    r = client.post(
        f"/api/inbox/conversations/{conv['id']}/save-contact", headers=_auth(admin_token)
    )
    assert r.status_code == 200, r.text
    c = r.json()
    assert c["telegram_user_id"] == 810030
    assert c["username"] == "unsavedpal"
    assert c["consent"] is True  # they messaged us first
    assert c["source"] == "inbox"

    # The conversation is now linked to the new contact.
    thread = client.get(
        f"/api/inbox/conversations/{conv['id']}", headers=_auth(admin_token)
    ).json()
    assert thread["conversation"]["contact_id"] == c["id"]
    assert thread["contact"]["id"] == c["id"]

    # Saving again is rejected.
    again = client.post(
        f"/api/inbox/conversations/{conv['id']}/save-contact", headers=_auth(admin_token)
    )
    assert again.status_code == 400


def test_incoming_from_known_contact_links_automatically(client, admin_token, monkeypatch):
    """A peer that already exists as a contact links without save-as-contact."""
    aid = _logged_in_account(client, admin_token, monkeypatch, "UX Known Acct")
    contact = client.post(
        "/api/contacts", headers=_auth(admin_token),
        json={"username": "@knownpal", "consent": True, "source": "online_store"},
    ).json()
    conv = _simulate(
        client, admin_token, aid,
        peer_id=810040, peer_name="Known Pal", peer_username="knownpal", text="hey",
    ).json()
    assert conv["contact_id"] == contact["id"]
    # Already linked -> save-as-contact is rejected.
    r = client.post(
        f"/api/inbox/conversations/{conv['id']}/save-contact", headers=_auth(admin_token)
    )
    assert r.status_code == 400
