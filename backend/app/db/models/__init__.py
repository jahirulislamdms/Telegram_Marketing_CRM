"""SQLAlchemy models.

Import each model here so it is registered on ``Base.metadata`` and picked up by
Alembic autogenerate. Models are added per build phase.
"""

from app.db.base import Base
from app.db.models.account import Account
from app.db.models.contact import Contact
from app.db.models.event import Event
from app.db.models.proxy import Proxy
from app.db.models.user import User
from app.db.models.warmup import WarmupParticipant, WarmupPartner, WarmupRun

__all__ = [
    "Base",
    "User",
    "Event",
    "Account",
    "Proxy",
    "Contact",
    "WarmupRun",
    "WarmupParticipant",
    "WarmupPartner",
]
