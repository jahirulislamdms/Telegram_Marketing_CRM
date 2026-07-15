"""Bot schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class BotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str | None
    username: str | None
    mode: str
    status: str
    created_at: datetime


class BotCreate(BaseModel):
    token: str = Field(min_length=10, max_length=255)


class BotDetail(BotOut):
    counts: dict
    deep_link: str


class SubscriberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    telegram_user_id: int
    name: str | None
    utm_source: str | None
    is_active: bool
    is_subscribed: bool


class BotConversationOut(BaseModel):
    id: int
    bot_id: int
    subscriber_id: int
    label: str
    last_message_at: str | None
    last_message_preview: str | None
    unread_count: int
    status: str


class BotMessageOut(BaseModel):
    id: int
    bot_conversation_id: int
    direction: str
    sender: str
    type: str
    body: str | None
    created_at: str | None


class BotThreadOut(BaseModel):
    conversation: BotConversationOut
    messages: list[BotMessageOut]


class ReplyRequest(BaseModel):
    text: str = Field(min_length=1)


class SendRequest(BaseModel):
    chat_id: int | str
    text: str = Field(min_length=1)


class PostRequest(BaseModel):
    chat_id: int | str
    text: str = ""
    image_url: str | None = None


class BroadcastRequest(BaseModel):
    text: str = Field(min_length=1)


class SimulateBotIncoming(BaseModel):
    telegram_user_id: int
    name: str | None = None
    text: str = Field(min_length=1)
    utm_source: str | None = None
