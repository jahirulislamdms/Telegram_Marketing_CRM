"""Shared enumerations used by models and Pydantic schemas.

Values are stored in the database as plain strings (with CHECK constraints) and
validated at the API boundary via these string enums.
"""

import enum


class UserRole(str, enum.Enum):
    admin = "admin"
    manager = "manager"
    agent = "agent"


class Theme(str, enum.Enum):
    dark = "dark"
    light = "light"


class ActorType(str, enum.Enum):
    user = "user"
    account = "account"
    system = "system"


class LeadType(str, enum.Enum):
    phone = "phone"
    username = "username"


class ResolutionStatus(str, enum.Enum):
    pending = "pending"
    resolved = "resolved"
    no_telegram = "no_telegram"
    failed = "failed"


class ContactStage(str, enum.Enum):
    new = "new"
    contacted = "contacted"
    replied = "replied"
    joined = "joined"
    customer = "customer"
    opted_out = "opted_out"


CONTACT_STAGES = [s.value for s in ContactStage]
