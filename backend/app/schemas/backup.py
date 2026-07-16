"""Backup & restore schemas (§15.2)."""

from pydantic import BaseModel, Field


class BackupOut(BaseModel):
    name: str
    size: int
    created_at: str
    scope: list[str]
    app_version: str | None = None
    db_file: str | None = None


class CreateBackup(BaseModel):
    # Omit/empty = everything.
    scope: list[str] = Field(default_factory=list)


class RestoreResult(BaseModel):
    name: str
    restored: list[str]


class BackupSettingsOut(BaseModel):
    enabled: bool
    interval_days: int
    scope: list[str]


class BackupSettingsIn(BaseModel):
    enabled: bool | None = None
    interval_days: int | None = Field(default=None, ge=1, le=365)
    scope: list[str] | None = None
