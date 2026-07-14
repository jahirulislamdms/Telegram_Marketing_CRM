"""Event / audit-log schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: str
    actor_type: str
    actor_id: int | None
    entity_ref: str | None
    meta: dict
    created_at: datetime
