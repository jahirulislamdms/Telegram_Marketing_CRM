"""Warmup schemas."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Stage(BaseModel):
    days: int = Field(ge=0)
    max_actions: int = Field(ge=0)


class WarmupRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    status: str
    stages: list
    groups: list
    messages: list
    min_delay_seconds: int
    max_delay_seconds: int
    created_at: datetime
    started_at: datetime | None


class WarmupRunCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    groups: list[str] = Field(default_factory=list)
    messages: list[str] = Field(default_factory=list)
    stages: list[Stage] | None = None
    min_delay_seconds: int = Field(default=40, ge=1)
    max_delay_seconds: int = Field(default=180, ge=1)


class ParticipantOut(BaseModel):
    id: int
    account_id: int
    account_label: str
    stage: int
    stage_progress: str
    actions_today: int
    status: str
    last_action_at: datetime | None
    joined: list


class PartnerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    identifier: str
    kind: str


class WarmupRunDetail(WarmupRunOut):
    participants: list[ParticipantOut]
    partners: list[PartnerOut]


class AddParticipants(BaseModel):
    account_ids: list[int] = Field(min_length=1)


class AddPartner(BaseModel):
    identifier: str = Field(min_length=2, max_length=255)
    kind: Literal["phone", "username"]


class TickResult(BaseModel):
    advanced: int
    completed: int
    actions: list
    errors: list
