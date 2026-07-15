"""Dashboard, analytics, and referral schemas.

Metric payloads are loosely typed (``dict``/``list``) because the aggregate shape
is driven by the analytics service; the API contract is exercised by the tests.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


# ---- Dashboard (system monitoring) ----


class DashboardSnapshot(BaseModel):
    generated_at: str
    accounts: dict
    caps: dict
    queue: dict
    proxies: dict
    throughput: dict
    running_campaigns: list
    recent_events: list


# ---- Marketing analytics ----


class AnalyticsOverview(BaseModel):
    funnel: dict
    per_source: list
    per_account: list
    campaigns: list
    utm: list
    referrals: list


# ---- Referrals ----


class ReferralOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    referrer_subscriber_id: int
    invite_code: str
    invited_count: int
    rewarded: bool
    created_at: datetime


class ReferralDetail(ReferralOut):
    deep_link: str


class CreateReferralRequest(BaseModel):
    subscriber_id: int


class RecordReferralRequest(BaseModel):
    invite_code: str = Field(min_length=1, max_length=80)


class RewardRequest(BaseModel):
    rewarded: bool = True
