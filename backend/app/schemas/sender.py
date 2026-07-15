"""Sender schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SendJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    template: str
    include_link: bool
    link_url: str | None
    suppress_link_first: bool
    active_start: str
    active_end: str
    status: str
    created_at: datetime
    started_at: datetime | None


class SendJobCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    template: str = Field(min_length=1)
    include_link: bool = False
    link_url: str | None = None
    suppress_link_first: bool = True


class TargetOut(BaseModel):
    id: int
    contact_id: int
    contact_label: str
    account_id: int | None
    status: str
    error: str | None
    rendered_body: str | None


class SendJobDetail(SendJobOut):
    stats: dict
    targets: list[TargetOut]


class AddTargets(BaseModel):
    contact_ids: list[int] | None = None
    source: str | None = None


class TickResult(BaseModel):
    sent: int
    skipped: int
    failed: int
    paused: bool
    actions: list
    warning: str | None = None
