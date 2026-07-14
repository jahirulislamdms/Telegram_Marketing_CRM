"""Contact schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.db.models.constants import ContactStage


class ContactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str | None
    display_label: str
    lead_type: str
    phone: str | None
    username: str | None
    telegram_user_id: int | None
    resolution_status: str
    source: str | None
    stage: str
    consent: bool
    opted_out: bool
    assigned_account_id: int | None
    assigned_agent_id: int | None
    utm: dict
    tags: list
    created_at: datetime
    last_contacted_at: datetime | None


class ContactCreate(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=32)
    username: str | None = Field(default=None, max_length=255)
    source: str | None = Field(default=None, max_length=120)
    consent: bool = False
    tags: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _need_identifier(self):
        if not (self.phone or self.username):
            raise ValueError("either phone or username is required")
        return self


class ContactUpdate(BaseModel):
    name: str | None = None
    source: str | None = None
    stage: ContactStage | None = None
    consent: bool | None = None
    opted_out: bool | None = None
    assigned_account_id: int | None = None
    assigned_agent_id: int | None = None
    tags: list[str] | None = None


class ImportResult(BaseModel):
    imported: int
    skipped_duplicates: int
    rejected_no_consent: int
    invalid: int
    total: int


class ResolveResult(BaseModel):
    id: int
    resolution_status: str
    telegram_user_id: int | None


class BulkResolveResult(BaseModel):
    resolved: int
    no_telegram: int
    failed: int


class MessageRequest(BaseModel):
    account_id: int
    text: str = Field(min_length=1)


class BulkStageUpdate(BaseModel):
    contact_ids: list[int] = Field(min_length=1)
    stage: ContactStage


class BulkAssign(BaseModel):
    contact_ids: list[int] = Field(min_length=1)
    assigned_agent_id: int | None = None


class BulkIds(BaseModel):
    contact_ids: list[int] = Field(min_length=1)
