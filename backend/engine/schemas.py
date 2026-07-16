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


class JoinRequest(Credentials):
    link: str


class SendRequest(Credentials):
    target: str
    text: str


class SendFile(Credentials):
    target: str
    file: str
    caption: str | None = None


class ResolveUsername(Credentials):
    username: str


class ResolvePhone(Credentials):
    phone: str


class ResolveDestination(Credentials):
    link: str


class AddMember(Credentials):
    entity_id: int
    target: str


class DownloadMedia(Credentials):
    peer: str
    message_id: int


class SendMedia(Credentials):
    target: str
    data_b64: str
    filename: str | None = None
    mime: str | None = None
    kind: str = "file"
    caption: str | None = None


# ---- Bots (Phase 10) ----


class BotStart(BaseModel):
    bot_id: int
    token: str


class BotInfo(BaseModel):
    token: str


class BotSend(BaseModel):
    bot_id: int
    token: str
    chat_id: int | str
    text: str


class BotPost(BaseModel):
    bot_id: int
    token: str
    chat_id: int | str
    text: str = ""
    image_url: str | None = None


class TelegramUser(BaseModel):
    id: int
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None
