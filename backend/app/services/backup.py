"""Backup & Restore center (§15.2).

A backup is a single ``.tar.gz`` in ``settings.backup_dir`` plus a small sidecar
``.meta.json`` (so listing never has to open the archive). Scope is selectable;
the default is everything:

* ``database`` — ``pg_dump --clean --if-exists`` on PostgreSQL, or a copy of the
  SQLite file in dev/tests.
* ``sessions`` — the Telethon session files, so restored accounts stay logged in.
* ``settings`` — the ``app_settings`` rows plus non-secret config. Raw ``.env``
  secrets are deliberately excluded from archives.

Archives contain session files and full database data — treat them as secret.
Every API around this is Admin-only.
"""

import json
import logging
import os
import shutil
import subprocess
import tarfile
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models.settings import AppSetting

log = logging.getLogger("backup")

PREFIX = "crm-backup-"
SUFFIX = ".tar.gz"
SCOPES = ("database", "sessions", "settings")
BACKUP_SETTINGS_KEY = "backup"
DEFAULT_BACKUP_SETTINGS = {"enabled": False, "interval_days": 1, "scope": list(SCOPES)}


def backup_dir() -> Path:
    return Path(settings.backup_dir)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ------------------------------------------------------------ path safety ----


def resolve_archive(name: str) -> Path:
    """Resolve a caller-supplied backup name to a path inside the backup dir.

    Rejects anything that isn't one of our plain archive filenames — this is the
    guard against path traversal on the download/delete/restore endpoints.
    """
    if (
        not name
        or "/" in name
        or "\\" in name
        or ".." in name
        or not name.startswith(PREFIX)
        or not name.endswith(SUFFIX)
    ):
        raise ValueError("invalid backup name")
    root = backup_dir().resolve()
    path = (root / name).resolve()
    if path.parent != root:
        raise ValueError("invalid backup name")
    return path


def _meta_path(archive: Path) -> Path:
    return archive.with_name(archive.name[: -len(SUFFIX)] + ".meta.json")


# --------------------------------------------------------------- database ----


def _sqlite_file() -> Path | None:
    url = settings.database_url
    if "sqlite" not in url:
        return None
    raw = url.split("///", 1)[1] if "///" in url else ""
    return Path(raw) if raw else None


def _dump_database(dest_dir: Path) -> str:
    """Dump the database into ``dest_dir``; returns the file name written."""
    if settings.database_url.startswith("postgresql"):
        out = dest_dir / "database.sql"
        env = {**os.environ, "PGPASSWORD": settings.postgres_password}
        cmd = [
            "pg_dump",
            "-h", settings.postgres_host,
            "-p", str(settings.postgres_port),
            "-U", settings.postgres_user,
            "-d", settings.postgres_db,
            "--clean",
            "--if-exists",
            "--no-owner",
            "-f", str(out),
        ]
        subprocess.run(cmd, check=True, env=env, capture_output=True, timeout=900)
        return out.name
    # SQLite (dev/tests): copy the database file.
    src = _sqlite_file()
    if src is None or not src.exists():
        raise RuntimeError("sqlite database file not found")
    out = dest_dir / "database.sqlite"
    shutil.copy2(src, out)
    return out.name


def _restore_database(src_dir: Path, db_file: str) -> None:
    src = src_dir / db_file
    if not src.exists():
        raise RuntimeError(f"backup is missing {db_file}")
    if settings.database_url.startswith("postgresql"):
        env = {**os.environ, "PGPASSWORD": settings.postgres_password}
        cmd = [
            "psql",
            "-h", settings.postgres_host,
            "-p", str(settings.postgres_port),
            "-U", settings.postgres_user,
            "-d", settings.postgres_db,
            "-v", "ON_ERROR_STOP=1",
            "-f", str(src),
        ]
        subprocess.run(cmd, check=True, env=env, capture_output=True, timeout=900)
        return
    dest = _sqlite_file()
    if dest is None:
        raise RuntimeError("sqlite database file not found")
    shutil.copy2(src, dest)


# --------------------------------------------------------------- settings ----


async def _export_settings(db: AsyncSession) -> dict:
    rows = (await db.execute(select(AppSetting))).scalars().all()
    return {
        "app_settings": {r.key: r.value for r in rows},
        # Non-secret tunables only — never the raw .env secrets.
        "config": {
            "app_version": settings.app_version,
            "rate_limit_enabled": settings.rate_limit_enabled,
            "rate_limit_per_minute": settings.rate_limit_per_minute,
            "rate_limit_login_per_minute": settings.rate_limit_login_per_minute,
            "send_min_delay_seconds": settings.send_min_delay_seconds,
            "send_max_delay_seconds": settings.send_max_delay_seconds,
            "warmup_full_daily_cap": settings.warmup_full_daily_cap,
            "auto_quarantine_on_warning": settings.auto_quarantine_on_warning,
        },
    }


async def _import_settings(db: AsyncSession, data: dict) -> int:
    """Restore app_settings rows (config tunables are informational only)."""
    count = 0
    for key, value in (data.get("app_settings") or {}).items():
        row = await db.get(AppSetting, key)
        if row is None:
            db.add(AppSetting(key=key, value=value))
        else:
            row.value = value
            row.updated_at = _now()
        count += 1
    await db.commit()
    return count


async def get_backup_settings(db: AsyncSession) -> dict:
    row = await db.get(AppSetting, BACKUP_SETTINGS_KEY)
    cfg = dict(DEFAULT_BACKUP_SETTINGS)
    if row is not None and isinstance(row.value, dict):
        cfg.update(row.value)
    return cfg


async def set_backup_settings(
    db: AsyncSession,
    *,
    enabled: bool | None = None,
    interval_days: int | None = None,
    scope: list[str] | None = None,
) -> dict:
    cfg = await get_backup_settings(db)
    if enabled is not None:
        cfg["enabled"] = bool(enabled)
    if interval_days is not None:
        cfg["interval_days"] = max(1, int(interval_days))
    if scope is not None:
        cfg["scope"] = [s for s in scope if s in SCOPES] or list(SCOPES)
    row = await db.get(AppSetting, BACKUP_SETTINGS_KEY)
    if row is None:
        db.add(AppSetting(key=BACKUP_SETTINGS_KEY, value=cfg))
    else:
        row.value = cfg
        row.updated_at = _now()
    await db.commit()
    return cfg


# ------------------------------------------------------------------ core -----


def list_backups() -> list[dict]:
    """Newest first. Reads the sidecar manifest; falls back to file stats."""
    root = backup_dir()
    if not root.exists():
        return []
    out: list[dict] = []
    for archive in root.glob(f"{PREFIX}*{SUFFIX}"):
        stat = archive.stat()
        meta = {
            "name": archive.name,
            "size": stat.st_size,
            "created_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
            "scope": [],
        }
        sidecar = _meta_path(archive)
        if sidecar.exists():
            try:
                meta.update(json.loads(sidecar.read_text()))
                meta["size"] = stat.st_size  # always trust the real size
            except Exception:  # noqa: BLE001
                pass
        out.append(meta)
    out.sort(key=lambda m: m["created_at"], reverse=True)
    return out


def prune_backups(keep: int | None = None) -> list[str]:
    """Keep only the newest ``keep`` archives; returns the pruned names."""
    keep = settings.backup_keep_last if keep is None else keep
    pruned = []
    for meta in list_backups()[keep:]:
        try:
            archive = resolve_archive(meta["name"])
            archive.unlink(missing_ok=True)
            _meta_path(archive).unlink(missing_ok=True)
            pruned.append(meta["name"])
        except Exception as exc:  # noqa: BLE001
            log.warning("prune failed for %s: %s", meta.get("name"), exc)
    return pruned


async def create_backup(db: AsyncSession, scope: list[str] | None = None) -> dict:
    """Create an archive of the selected components (default: everything)."""
    chosen = [s for s in (scope or SCOPES) if s in SCOPES] or list(SCOPES)
    root = backup_dir()
    root.mkdir(parents=True, exist_ok=True)
    created = _now()
    archive = root / f"{PREFIX}{created.strftime('%Y%m%d-%H%M%S')}{SUFFIX}"

    manifest: dict = {
        "created_at": created.isoformat(),
        "scope": [],
        "app_version": settings.app_version,
        "db_file": None,
    }
    with tempfile.TemporaryDirectory() as tmp:
        staging = Path(tmp)
        if "database" in chosen:
            manifest["db_file"] = _dump_database(staging)
            manifest["scope"].append("database")
        if "sessions" in chosen:
            src = Path(settings.sessions_dir)
            if src.exists():
                shutil.copytree(src, staging / "sessions")
            else:
                (staging / "sessions").mkdir()
            manifest["scope"].append("sessions")
        if "settings" in chosen:
            (staging / "settings.json").write_text(
                json.dumps(await _export_settings(db), indent=2)
            )
            manifest["scope"].append("settings")
        (staging / "manifest.json").write_text(json.dumps(manifest, indent=2))

        with tarfile.open(archive, "w:gz") as tar:
            for item in sorted(staging.iterdir()):
                tar.add(item, arcname=item.name)

    meta = {**manifest, "name": archive.name, "size": archive.stat().st_size}
    _meta_path(archive).write_text(json.dumps(meta, indent=2))
    prune_backups()
    log.info("backup created: %s (%s)", archive.name, ", ".join(manifest["scope"]))
    return meta


def _validate_archive(path: Path) -> dict:
    """Confirm a file really is one of our backups; returns its manifest."""
    try:
        with tarfile.open(path, "r:gz") as tar:
            if "manifest.json" not in tar.getnames():
                raise ValueError("not a CRM backup archive (manifest.json missing)")
            member = tar.extractfile("manifest.json")
            manifest = json.loads(member.read()) if member else None
    except tarfile.TarError as exc:
        raise ValueError(f"not a valid .tar.gz archive ({exc})")
    except json.JSONDecodeError:
        raise ValueError("backup manifest is not valid JSON")
    if not isinstance(manifest, dict) or not manifest.get("scope"):
        raise ValueError("backup manifest is invalid")
    return manifest


def save_uploaded_backup(data: bytes, filename: str | None = None) -> dict:
    """Load a previously downloaded backup back onto the server (§15.2.f).

    The file is validated as a real CRM archive before it is accepted, then
    stored under a fresh (collision-safe) name so it sorts as the newest entry
    and can't be pruned out from under the operator. Its *original* creation
    time is kept in the metadata for display. Restoring it afterwards uses the
    normal restore flow.
    """
    if not data:
        raise ValueError("empty file")
    limit = settings.backup_max_upload_mb * 1024 * 1024
    if len(data) > limit:
        raise ValueError(f"file too large (max {settings.backup_max_upload_mb} MB)")

    root = backup_dir()
    root.mkdir(parents=True, exist_ok=True)
    tmp_fd = tempfile.NamedTemporaryFile(dir=root, suffix=".part", delete=False)
    try:
        tmp_fd.write(data)
        tmp_fd.close()
        tmp_path = Path(tmp_fd.name)
        manifest = _validate_archive(tmp_path)  # raises ValueError if not ours
    except ValueError:
        Path(tmp_fd.name).unlink(missing_ok=True)
        raise
    except Exception:
        Path(tmp_fd.name).unlink(missing_ok=True)
        raise

    uploaded_at = _now()
    base = f"{PREFIX}{uploaded_at.strftime('%Y%m%d-%H%M%S')}"
    archive = root / f"{base}{SUFFIX}"
    counter = 1
    while archive.exists():
        archive = root / f"{base}-{counter}{SUFFIX}"
        counter += 1
    tmp_path.replace(archive)

    meta = {
        "name": archive.name,
        "size": archive.stat().st_size,
        "created_at": uploaded_at.isoformat(),
        "scope": manifest.get("scope", []),
        "app_version": manifest.get("app_version"),
        "db_file": manifest.get("db_file"),
        "original_created_at": manifest.get("created_at"),
        "uploaded": True,
    }
    _meta_path(archive).write_text(json.dumps(meta, indent=2))
    # Deliberately no prune here: a just-uploaded archive must not be deleted.
    log.info("backup uploaded: %s (from %s)", archive.name, filename or "?")
    return meta


def delete_backup(name: str) -> None:
    archive = resolve_archive(name)
    if not archive.exists():
        raise FileNotFoundError(name)
    archive.unlink()
    _meta_path(archive).unlink(missing_ok=True)


async def restore_backup(db: AsyncSession, name: str) -> dict:
    """Restore an archive over the running system (disruptive — confirm first)."""
    archive = resolve_archive(name)
    if not archive.exists():
        raise FileNotFoundError(name)
    restored: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        staging = Path(tmp)
        with tarfile.open(archive, "r:gz") as tar:
            # Guard against path traversal inside the archive itself.
            for member in tar.getmembers():
                target = (staging / member.name).resolve()
                if not str(target).startswith(str(staging.resolve())):
                    raise ValueError("unsafe archive member")
            tar.extractall(staging)

        manifest = {}
        mpath = staging / "manifest.json"
        if mpath.exists():
            manifest = json.loads(mpath.read_text())
        scope = manifest.get("scope") or []

        if "sessions" in scope and (staging / "sessions").exists():
            dest = Path(settings.sessions_dir)
            dest.mkdir(parents=True, exist_ok=True)
            for item in (staging / "sessions").iterdir():
                shutil.copy2(item, dest / item.name)
            restored.append("sessions")
        if "settings" in scope and (staging / "settings.json").exists():
            await _import_settings(db, json.loads((staging / "settings.json").read_text()))
            restored.append("settings")
        # Database last: it can drop/recreate objects under the running app.
        if "database" in scope and manifest.get("db_file"):
            _restore_database(staging, manifest["db_file"])
            restored.append("database")

    log.warning("backup restored: %s (%s)", name, ", ".join(restored))
    return {"name": name, "restored": restored}


# ------------------------------------------------------- auto-backup tick ----


def is_due(cfg: dict, backups: list[dict] | None = None) -> bool:
    """True when auto-backup is on and the newest archive is older than the interval."""
    if not cfg.get("enabled"):
        return False
    items = list_backups() if backups is None else backups
    if not items:
        return True
    try:
        newest = datetime.fromisoformat(items[0]["created_at"])
    except (ValueError, KeyError):
        return True
    if newest.tzinfo is None:
        newest = newest.replace(tzinfo=timezone.utc)
    return _now() - newest >= timedelta(days=max(1, int(cfg.get("interval_days", 1))))
