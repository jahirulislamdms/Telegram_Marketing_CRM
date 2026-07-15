"""Destination & add-members schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DestinationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str | None
    link: str
    tg_entity_id: int | None
    type: str
    invite_link: str | None
    created_at: datetime


class DestinationCreate(BaseModel):
    link: str = Field(min_length=3, max_length=500)


class MembershipOut(BaseModel):
    id: int
    contact_id: int
    contact_label: str
    state: str
    method: str | None
    account_id: int | None
    error: str | None


class DestinationDetail(DestinationOut):
    stats: dict
    memberships: list[MembershipOut]


class AddMembersRequest(BaseModel):
    contact_ids: list[int] | None = None
    identifiers: list[str] | None = None


class AddMembersResult(BaseModel):
    queued: int
    skipped_existing: int


class AddTickResult(BaseModel):
    added: int
    invited: int
    failed: int
    paused: bool
    actions: list
    warning: str | None = None
