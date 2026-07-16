"""Inbox schemas."""

from typing import Literal

from pydantic import BaseModel, Field

CONVERSATION_STATUSES = (
    "new",
    "contacted",
    "replied",
    "joined",
    "customer",
    "opted_out",
    "blocked",
)


class ConversationOut(BaseModel):
    id: int
    contact_id: int | None
    account_id: int
    account_label: str
    peer_id: int | None
    peer_username: str | None
    label: str
    last_message_at: str | None
    last_message_preview: str | None
    unread_count: int
    status: str
    archived: bool


class MessageOut(BaseModel):
    id: int
    conversation_id: int
    direction: str
    account_id: int | None
    sender: str
    type: str
    body: str | None
    media_ref: str | None
    status: str
    created_at: str | None


class ThreadOut(BaseModel):
    conversation: ConversationOut
    messages: list[MessageOut]
    contact: dict | None


class SendReply(BaseModel):
    type: Literal["text", "link", "image"] = "text"
    body: str | None = None
    media_url: str | None = None


class SetArchived(BaseModel):
    archived: bool = True


class SetStatus(BaseModel):
    status: Literal[
        "new", "contacted", "replied", "joined", "customer", "opted_out", "blocked"
    ]


class SimulateIncoming(BaseModel):
    account_id: int
    peer_id: int | None = None
    peer_name: str | None = None
    peer_username: str | None = None
    text: str | None = None
    msg_type: str | None = None
    media_ref: str | None = None
    tg_message_id: int | None = None


class BulkIds(BaseModel):
    conversation_ids: list[int] = Field(min_length=1)


class BulkStatus(BulkIds):
    status: Literal[
        "new", "contacted", "replied", "joined", "customer", "opted_out", "blocked"
    ]
