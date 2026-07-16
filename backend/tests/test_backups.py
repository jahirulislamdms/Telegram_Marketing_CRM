"""Phase 15.2 — Backup & Restore center.

Exercises the real archive path (SQLite dialect: the DB file is copied), so the
tests point ``backup_dir`` at a temp directory.
"""

import asyncio
import json
import pathlib
import tarfile
import tempfile
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.db.models.settings import AppSetting
from app.services import backup as backup_service

# Mirrors conftest: the suite's SQLite database file.
_TEST_DB = pathlib.Path(tempfile.gettempdir()) / "tgcrm_test.db"
_TEST_DB_URL = f"sqlite+aiosqlite:///{_TEST_DB.as_posix()}"


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
def backup_root(tmp_path, monkeypatch) -> Path:
    """Isolate each test's archives, and point the dump at the test SQLite DB.

    ``settings.database_url`` otherwise defaults to Postgres (conftest only
    overrides the ``get_db`` dependency), which would make the service shell out
    to pg_dump.
    """
    root = tmp_path / "backups"
    monkeypatch.setattr(settings, "backup_dir", str(root))
    monkeypatch.setattr(settings, "database_url_env", _TEST_DB_URL)
    return root


@pytest.fixture()
def clear_backup_setting():
    """The app_settings row survives in the shared test DB — reset it."""

    async def _clear():
        engine = create_async_engine(_TEST_DB_URL, poolclass=NullPool)
        session = async_sessionmaker(engine, expire_on_commit=False)
        async with session() as db:
            row = await db.get(AppSetting, backup_service.BACKUP_SETTINGS_KEY)
            if row is not None:
                await db.delete(row)
                await db.commit()
        await engine.dispose()

    asyncio.run(_clear())


@pytest.fixture()
def sessions_dir(tmp_path, monkeypatch) -> Path:
    d = tmp_path / "sessions"
    d.mkdir()
    (d / "7.session").write_bytes(b"fake-telethon-session")
    monkeypatch.setattr(settings, "sessions_dir", str(d))
    return d


# --------------------------------------------------------- create / list -----


def test_create_backup_includes_all_scopes(client, admin_token, backup_root, sessions_dir):
    r = client.post("/api/backups", headers=_auth(admin_token), json={"scope": []})
    assert r.status_code == 201, r.text
    meta = r.json()
    assert set(meta["scope"]) == {"database", "sessions", "settings"}  # default = everything
    assert meta["size"] > 0

    archive = backup_root / meta["name"]
    assert archive.exists()
    with tarfile.open(archive, "r:gz") as tar:
        names = set(tar.getnames())
    assert "manifest.json" in names
    assert "database.sqlite" in names  # SQLite dialect in tests
    assert "settings.json" in names
    assert any(n.startswith("sessions") for n in names)

    listed = client.get("/api/backups", headers=_auth(admin_token)).json()
    assert any(b["name"] == meta["name"] for b in listed)


def test_create_backup_with_selected_scope_only(client, admin_token, backup_root, sessions_dir):
    r = client.post("/api/backups", headers=_auth(admin_token), json={"scope": ["settings"]})
    assert r.status_code == 201, r.text
    meta = r.json()
    assert meta["scope"] == ["settings"]
    with tarfile.open(backup_root / meta["name"], "r:gz") as tar:
        names = set(tar.getnames())
    assert "settings.json" in names
    assert "database.sqlite" not in names


def test_prune_keeps_only_the_newest_n(backup_root, monkeypatch):
    """A 6th backup prunes the oldest (spec: keep the last 5)."""
    monkeypatch.setattr(settings, "backup_keep_last", 5)
    backup_root.mkdir(parents=True)
    names = []
    for day in range(1, 7):  # six archives, oldest first
        stem = f"{backup_service.PREFIX}202601{day:02d}-000000"
        name = f"{stem}{backup_service.SUFFIX}"
        (backup_root / name).write_bytes(b"archive")
        (backup_root / f"{stem}.meta.json").write_text(
            json.dumps(
                {
                    "name": name,
                    "created_at": f"2026-01-{day:02d}T00:00:00+00:00",
                    "scope": ["settings"],
                    "size": 7,
                }
            )
        )
        names.append(name)

    assert len(backup_service.list_backups()) == 6
    pruned = backup_service.prune_backups()
    remaining = {b["name"] for b in backup_service.list_backups()}
    assert len(remaining) == 5
    assert names[0] in pruned and names[0] not in remaining  # oldest gone
    assert names[5] in remaining  # newest kept
    # The sidecar goes with it.
    assert not (backup_root / f"{names[0][: -len(backup_service.SUFFIX)]}.meta.json").exists()


# ------------------------------------------------------ download / delete ----


def test_download_and_delete_backup(client, admin_token, backup_root, sessions_dir):
    meta = client.post(
        "/api/backups", headers=_auth(admin_token), json={"scope": ["settings"]}
    ).json()

    dl = client.get(f"/api/backups/{meta['name']}/download", headers=_auth(admin_token))
    assert dl.status_code == 200
    assert dl.content[:2] == b"\x1f\x8b"  # gzip magic

    d = client.delete(f"/api/backups/{meta['name']}", headers=_auth(admin_token))
    assert d.status_code == 204
    assert not (backup_root / meta["name"]).exists()
    assert client.get("/api/backups", headers=_auth(admin_token)).json() == []


@pytest.mark.parametrize(
    "bad",
    ["../../etc/passwd", "crm-backup-../x.tar.gz", "notabackup.tar.gz", "crm-backup-x.txt"],
)
def test_path_traversal_and_bad_names_rejected(client, admin_token, backup_root, bad):
    r = client.get(f"/api/backups/{bad}/download", headers=_auth(admin_token))
    assert r.status_code in (400, 404)  # never 200, never escapes the backup dir


# ------------------------------------------------------------- restore -------


def test_restore_round_trip_restores_sessions_and_settings(
    client, admin_token, backup_root, sessions_dir
):
    # A setting we can watch change.
    client.put(
        "/api/backups/settings", headers=_auth(admin_token),
        json={"enabled": True, "interval_days": 7},
    )
    meta = client.post(
        "/api/backups", headers=_auth(admin_token), json={"scope": ["sessions", "settings"]}
    ).json()

    # Mutate the world after the backup.
    client.put(
        "/api/backups/settings", headers=_auth(admin_token),
        json={"enabled": False, "interval_days": 30},
    )
    (sessions_dir / "7.session").unlink()

    r = client.post(f"/api/backups/{meta['name']}/restore", headers=_auth(admin_token))
    assert r.status_code == 200, r.text
    assert set(r.json()["restored"]) == {"sessions", "settings"}

    # Session file is back, settings reverted to the backed-up values.
    assert (sessions_dir / "7.session").read_bytes() == b"fake-telethon-session"
    cfg = client.get("/api/backups/settings", headers=_auth(admin_token)).json()
    assert cfg["enabled"] is True and cfg["interval_days"] == 7


def test_restore_unknown_backup_404(client, admin_token, backup_root):
    r = client.post(
        f"/api/backups/{backup_service.PREFIX}20990101-000000.tar.gz/restore",
        headers=_auth(admin_token),
    )
    assert r.status_code == 404


# ------------------------------------------------- auto-backup settings ------


def test_backup_settings_defaults_and_update(
    client, admin_token, backup_root, clear_backup_setting
):
    cfg = client.get("/api/backups/settings", headers=_auth(admin_token)).json()
    assert cfg["enabled"] is False and cfg["interval_days"] == 1
    assert set(cfg["scope"]) == {"database", "sessions", "settings"}

    saved = client.put(
        "/api/backups/settings", headers=_auth(admin_token),
        json={"enabled": True, "interval_days": 3, "scope": ["database"]},
    ).json()
    assert saved == {"enabled": True, "interval_days": 3, "scope": ["database"]}
    # Persisted.
    assert client.get("/api/backups/settings", headers=_auth(admin_token)).json() == saved


def test_interval_days_validated(client, admin_token, backup_root):
    r = client.put(
        "/api/backups/settings", headers=_auth(admin_token), json={"interval_days": 0}
    )
    assert r.status_code == 422


def test_is_due_respects_enabled_and_interval():
    assert backup_service.is_due({"enabled": False, "interval_days": 1}, []) is False
    assert backup_service.is_due({"enabled": True, "interval_days": 1}, []) is True  # none yet
    fresh = [{"created_at": backup_service._now().isoformat()}]
    assert backup_service.is_due({"enabled": True, "interval_days": 1}, fresh) is False


# ---------------------------------------------------------------- RBAC -------


def test_backups_are_admin_only(client, admin_token, backup_root):
    client.post(
        "/api/users", headers=_auth(admin_token),
        json={"email": "mgr152@test.com", "password": "MgrPass123", "role": "manager"},
    )
    mgr = _login(client, "mgr152@test.com", "MgrPass123")
    assert client.get("/api/backups", headers=_auth(mgr)).status_code == 403
    assert client.post("/api/backups", headers=_auth(mgr), json={"scope": []}).status_code == 403
    assert client.get("/api/backups/settings", headers=_auth(mgr)).status_code == 403
