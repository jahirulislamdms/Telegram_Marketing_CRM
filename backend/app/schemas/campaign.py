"""Template & campaign schemas."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# ---- Templates ----


class TemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    body: str
    include_link: bool
    link_url: str | None
    variant_group: str
    variant_label: str
    created_at: datetime


class TemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    body: str = Field(min_length=1)
    include_link: bool = False
    link_url: str | None = None
    variant_group: str = Field(min_length=1, max_length=60)
    variant_label: str = Field(default="A", max_length=10)


# ---- Campaigns ----


class Segment(BaseModel):
    source: str | None = None
    stage: str | None = None
    tag: str | None = None
    exclude_in_destination: int | None = None


class CampaignStep(BaseModel):
    offset_hours: int = Field(default=0, ge=0)
    variant_group: str | None = None


class CampaignOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    action: str
    destination_id: int | None
    segment: dict
    steps: list
    ab_test: bool
    status: str
    created_at: datetime
    started_at: datetime | None


class CampaignCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    action: Literal["message", "invite", "add"] = "message"
    destination_id: int | None = None
    segment: Segment = Field(default_factory=Segment)
    steps: list[CampaignStep] = Field(min_length=1)
    ab_test: bool = False


class CampaignTargetOut(BaseModel):
    id: int
    contact_id: int
    contact_label: str
    step: int
    template_id: int | None
    account_id: int | None
    result: str
    error: str | None


class CampaignDetail(CampaignOut):
    stats: dict
    ab_report: list
    targets: list[CampaignTargetOut]


class CampaignTickResult(BaseModel):
    sent: int
    joined: int
    failed: int
    skipped: int
    paused: bool
    actions: list
    warning: str | None = None
