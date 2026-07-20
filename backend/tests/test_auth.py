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


# ----------------------------------------- §15.4 profile / staff management ---


def test_profile_update_name_and_email(client, admin_credentials):
    admin = _login(client, **admin_credentials)
    r = client.patch(
        "/api/auth/me",
        headers=_auth(admin["access_token"]),
        json={"full_name": "Admin Renamed", "email": "admin@test.com"},  # same email = ok
    )
    assert r.status_code == 200, r.text
    assert r.json()["full_name"] == "Admin Renamed"
    assert r.json()["email"] == "admin@test.com"


def test_profile_name_cannot_be_empty(client, admin_credentials):
    admin = _login(client, **admin_credentials)
    r = client.patch(
        "/api/auth/me", headers=_auth(admin["access_token"]), json={"full_name": "   "}
    )
    assert r.status_code == 422
    assert r.json()["detail"] == "Name cannot be empty."


def test_profile_email_must_be_unique(client, admin_credentials):
    admin = _login(client, **admin_credentials)
    client.post(
        "/api/users",
        headers=_auth(admin["access_token"]),
        json={"email": "p154_taken@test.com", "password": "TakenPass123", "role": "agent"},
    )
    r = client.patch(
        "/api/auth/me",
        headers=_auth(admin["access_token"]),
        json={"email": "p154_taken@test.com"},
    )
    assert r.status_code == 409
    assert r.json()["detail"] == "This email address is already in use."


def test_change_password_flow(client, admin_credentials):
    admin = _login(client, **admin_credentials)
    client.post(
        "/api/users",
        headers=_auth(admin["access_token"]),
        json={"email": "p154_pw@test.com", "password": "OrigPass123", "role": "agent"},
    )
    user = _login(client, "p154_pw@test.com", "OrigPass123")
    tok = _auth(user["access_token"])

    # Wrong current password is rejected.
    bad = client.post(
        "/api/auth/change-password",
        headers=tok,
        json={"current_password": "WRONGPASS", "new_password": "NewPass456"},
    )
    assert bad.status_code == 400
    assert bad.json()["detail"] == "Current password is incorrect."

    # Correct current password succeeds and does NOT log the user out.
    ok = client.post(
        "/api/auth/change-password",
        headers=tok,
        json={"current_password": "OrigPass123", "new_password": "NewPass456"},
    )
    assert ok.status_code == 200
    assert ok.json()["detail"] == "Password changed successfully."
    assert client.get("/api/auth/me", headers=tok).status_code == 200  # token still valid

    # Old password no longer works; new one does.
    assert client.post(
        "/api/auth/login", json={"email": "p154_pw@test.com", "password": "OrigPass123"}
    ).status_code == 401
    assert client.post(
        "/api/auth/login", json={"email": "p154_pw@test.com", "password": "NewPass456"}
    ).status_code == 200


def test_change_password_min_length(client, admin_credentials):
    admin = _login(client, **admin_credentials)
    r = client.post(
        "/api/auth/change-password",
        headers=_auth(admin["access_token"]),
        json={"current_password": admin_credentials["password"], "new_password": "short"},
    )
    assert r.status_code == 422  # pydantic min_length=8


def test_staff_edit_name_email_role(client, admin_credentials):
    admin = _login(client, **admin_credentials)
    created = client.post(
        "/api/users",
        headers=_auth(admin["access_token"]),
        json={"email": "p154_edit@test.com", "password": "EditPass123", "role": "agent"},
    ).json()
    r = client.patch(
        f"/api/users/{created['id']}",
        headers=_auth(admin["access_token"]),
        json={"full_name": "Edited Staff", "email": "p154_edit2@test.com", "role": "manager"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["full_name"] == "Edited Staff"
    assert body["email"] == "p154_edit2@test.com"
    assert body["role"] == "manager"


def test_staff_edit_duplicate_email_conflict(client, admin_credentials):
    admin = _login(client, **admin_credentials)
    client.post(
        "/api/users", headers=_auth(admin["access_token"]),
        json={"email": "p154_a@test.com", "password": "PassAAA123", "role": "agent"},
    )
    b = client.post(
        "/api/users", headers=_auth(admin["access_token"]),
        json={"email": "p154_b@test.com", "password": "PassBBB123", "role": "agent"},
    ).json()
    r = client.patch(
        f"/api/users/{b['id']}",
        headers=_auth(admin["access_token"]),
        json={"email": "p154_a@test.com"},
    )
    assert r.status_code == 409
    assert r.json()["detail"] == "This email address is already in use."


def test_staff_edit_password_optional(client, admin_credentials):
    admin = _login(client, **admin_credentials)
    created = client.post(
        "/api/users", headers=_auth(admin["access_token"]),
        json={"email": "p154_pwopt@test.com", "password": "StartPass123", "role": "agent"},
    ).json()
    # Update name only (no password) — login still works with the original password.
    client.patch(
        f"/api/users/{created['id']}",
        headers=_auth(admin["access_token"]),
        json={"full_name": "Kept Password"},
    )
    assert client.post(
        "/api/auth/login", json={"email": "p154_pwopt@test.com", "password": "StartPass123"}
    ).status_code == 200
    # Provide a new password — login updates.
    client.patch(
        f"/api/users/{created['id']}",
        headers=_auth(admin["access_token"]),
        json={"password": "ChangedPass456"},
    )
    assert client.post(
        "/api/auth/login", json={"email": "p154_pwopt@test.com", "password": "ChangedPass456"}
    ).status_code == 200


def test_staff_edit_name_required(client, admin_credentials):
    admin = _login(client, **admin_credentials)
    created = client.post(
        "/api/users", headers=_auth(admin["access_token"]),
        json={"email": "p154_req@test.com", "password": "ReqPass123", "role": "agent"},
    ).json()
    r = client.patch(
        f"/api/users/{created['id']}",
        headers=_auth(admin["access_token"]),
        json={"full_name": "  "},
    )
    assert r.status_code == 422
    assert r.json()["detail"] == "Name is required."
