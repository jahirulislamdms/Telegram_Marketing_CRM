"""Account schemas."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    label: str
    phone: str | None
    api_id: str | None
    session_ref: str | None
    proxy_id: int | None
    status: str
    warmup_stage: int
    daily_cap: int
    actions_today: int
    last_action_at: datetime | None
    spam_state: str
    created_at: datetime


class AccountCreate(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    phone: str | None = Field(default=None, max_length=32)
    # Optional per-account API credentials; blank uses the shared API ID/HASH.
    api_id: str | None = Field(default=None, max_length=32)
    api_hash: str | None = Field(default=None, max_length=64)
    # If true (default), auto-assign a free healthy proxy from the pool.
    assign_proxy: bool = True


class AccountStatus(BaseModel):
    """Live status merged from the DB row and the engine."""

    id: int
    label: str
    status: str
    connected: bool = False
    authorized: bool = False
    telegram_user: dict | None = None
    engine_reachable: bool = True
    detail: str | None = None


# ---- Login flow payloads ----


class PhoneSendCodeRequest(BaseModel):
    phone: str = Field(min_length=3, max_length=32)


class PhoneSendCodeResponse(BaseModel):
    phone_code_hash: str


class PhoneSignInRequest(BaseModel):
    phone: str
    code: str
    phone_code_hash: str
    password: str | None = None


class SessionStringImport(BaseModel):
    session_string: str = Field(min_length=10)


class QrLoginResponse(BaseModel):
    url: str
    expires_at: datetime | None = None


class QrStatusResponse(BaseModel):
    # waiting | password_needed | authorized | expired | error
    status: str
    url: str | None = None
    telegram_user: dict | None = None
    detail: str | None = None


class PasswordRequest(BaseModel):
    password: str = Field(min_length=1)


class LoginResultResponse(BaseModel):
    # authorized | password_needed | error
    status: str
    telegram_user: dict | None = None
    detail: str | None = None


# ---- Health / status (Phase 3) ----


class AccountStatusUpdate(BaseModel):
    status: Literal["active", "warming", "quarantined", "banned", "logged_out"]


class SpamCheckResult(BaseModel):
    spam_state: str  # clean | limited | banned | unknown
    reply: str | None = None
    quarantined: bool = False
    detail: str | None = None


class BanCheckResult(BaseModel):
    state: str  # ok | banned | unauthorized | error
    telegram_user: dict | None = None
    status: str  # the account's resulting status
    detail: str | None = None


class AppealResult(BaseModel):
    submitted: bool
    reply: str | None = None
    detail: str | None = None
