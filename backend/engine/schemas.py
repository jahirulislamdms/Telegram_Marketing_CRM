"""Pydantic models for the engine's internal HTTP API."""

from pydantic import BaseModel


class ProxySpec(BaseModel):
    type: str
    host: str
    port: int
    username: str | None = None
    password: str | None = None


class Credentials(BaseModel):
    api_id: str
    api_hash: str
    proxy: ProxySpec | None = None


class SessionImport(Credentials):
    session_string: str


class PhoneSendCode(Credentials):
    phone: str


class PhoneSignIn(BaseModel):
    phone: str
    code: str
    phone_code_hash: str
    password: str | None = None


class PasswordSubmit(BaseModel):
    password: str


class TelegramUser(BaseModel):
    id: int
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None
