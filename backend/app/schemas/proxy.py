"""Proxy schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ProxyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: str
    host: str
    port: int
    username: str | None
    is_active: bool
    assigned_account_id: int | None
    health: str
    last_checked_at: datetime | None
    notes: str | None
    created_at: datetime


class ProxyImportRequest(BaseModel):
    # Bulk paste: one proxy per line. Supported formats:
    #   host:port | host:port:user:pass | socks5://user:pass@host:port
    raw: str


class ProxyImportResult(BaseModel):
    imported: int
    skipped_duplicates: int
    invalid: list[str]
    total_in_pool: int
