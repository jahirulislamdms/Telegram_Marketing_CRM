"""Phase 1 acceptance: auth flow + RBAC.

Done when: admin can log in, create staff, and roles are enforced.
"""


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _login(client, email: str, password: str) -> dict:
    resp = client.post("/api/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_login_success(client, admin_credentials):
    resp = client.post("/api/auth/login", json=admin_credentials)
    assert resp.status_code == 200
    body = resp.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["token_type"] == "bearer"


def test_login_wrong_password(client):
    resp = client.post(
        "/api/auth/login", json={"email": "admin@test.com", "password": "wrong"}
    )
    assert resp.status_code == 401


def test_me_requires_auth(client):
    assert client.get("/api/auth/me").status_code == 401


def test_me_returns_current_admin(client, admin_credentials):
    tokens = _login(client, **admin_credentials)
    resp = client.get("/api/auth/me", headers=_auth(tokens["access_token"]))
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == "admin@test.com"
    assert body["role"] == "admin"


def test_admin_creates_staff_and_roles_enforced(client, admin_credentials):
    admin = _login(client, **admin_credentials)

    created_manager = client.post(
        "/api/users",
        headers=_auth(admin["access_token"]),
        json={
            "email": "manager@test.com",
            "password": "ManagerPass123",
            "full_name": "Manager One",
            "role": "manager",
        },
    )
    assert created_manager.status_code == 201, created_manager.text
    assert created_manager.json()["role"] == "manager"

    created_agent = client.post(
        "/api/users",
        headers=_auth(admin["access_token"]),
        json={"email": "agent@test.com", "password": "AgentPass123", "role": "agent"},
    )
    assert created_agent.status_code == 201

    # A manager must NOT be able to list or create staff (admin-only).
    manager = _login(client, "manager@test.com", "ManagerPass123")
    assert client.get("/api/users", headers=_auth(manager["access_token"])).status_code == 403
    forbidden = client.post(
        "/api/users",
        headers=_auth(manager["access_token"]),
        json={"email": "x@test.com", "password": "Password123", "role": "agent"},
    )
    assert forbidden.status_code == 403

    # Admin can list all staff.
    listing = client.get("/api/users", headers=_auth(admin["access_token"]))
    assert listing.status_code == 200
    emails = {u["email"] for u in listing.json()}
    assert {"admin@test.com", "manager@test.com", "agent@test.com"} <= emails


def test_duplicate_email_conflict(client, admin_credentials):
    admin = _login(client, **admin_credentials)
    resp = client.post(
        "/api/users",
        headers=_auth(admin["access_token"]),
        json={"email": "admin@test.com", "password": "Another123", "role": "agent"},
    )
    assert resp.status_code == 409


def test_refresh_flow(client, admin_credentials):
    admin = _login(client, **admin_credentials)
    ok = client.post("/api/auth/refresh", json={"refresh_token": admin["refresh_token"]})
    assert ok.status_code == 200
    assert ok.json()["access_token"]
    # An access token must not be accepted where a refresh token is required.
    bad = client.post("/api/auth/refresh", json={"refresh_token": admin["access_token"]})
    assert bad.status_code == 401


def test_update_own_theme(client, admin_credentials):
    admin = _login(client, **admin_credentials)
    resp = client.patch(
        "/api/auth/me", headers=_auth(admin["access_token"]), json={"theme": "light"}
    )
    assert resp.status_code == 200
    assert resp.json()["theme"] == "light"


def test_deactivated_user_cannot_login(client, admin_credentials):
    admin = _login(client, **admin_credentials)
    created = client.post(
        "/api/users",
        headers=_auth(admin["access_token"]),
        json={"email": "temp@test.com", "password": "TempPass123", "role": "agent"},
    )
    assert created.status_code == 201
    user_id = created.json()["id"]

    deactivated = client.delete(
        f"/api/users/{user_id}", headers=_auth(admin["access_token"])
    )
    assert deactivated.status_code == 200
    assert deactivated.json()["is_active"] is False

    blocked = client.post(
        "/api/auth/login", json={"email": "temp@test.com", "password": "TempPass123"}
    )
    assert blocked.status_code == 401


def test_admin_cannot_deactivate_self(client, admin_credentials):
    admin = _login(client, **admin_credentials)
    me = client.get("/api/auth/me", headers=_auth(admin["access_token"])).json()
    resp = client.delete(f"/api/users/{me['id']}", headers=_auth(admin["access_token"]))
    assert resp.status_code == 400


def test_audit_log_records_actions(client, admin_credentials):
    admin = _login(client, **admin_credentials)
    resp = client.get("/api/audit", headers=_auth(admin["access_token"]))
    assert resp.status_code == 200
    types = {event["type"] for event in resp.json()}
    assert "user.login" in types
    assert "user.create" in types
