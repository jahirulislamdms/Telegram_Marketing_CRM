"""Pacing helpers: rotation, per-account caps, delays, and active-hour windows."""

import random
from datetime import datetime, time


def under_daily_cap(actions_today: int, daily_cap: int) -> bool:
    return actions_today < daily_cap


def delay_ok(last_action_at: datetime | None, now: datetime, min_delay_seconds: int) -> bool:
    if last_action_at is None:
        return True
    if last_action_at.tzinfo is None:
        last_action_at = last_action_at.replace(tzinfo=now.tzinfo)
    return (now - last_action_at).total_seconds() >= min_delay_seconds


def random_delay(min_seconds: int, max_seconds: int, rng: random.Random | None = None) -> int:
    rng = rng or random
    lo, hi = sorted((min_seconds, max_seconds))
    return rng.randint(lo, hi)


def _parse_hhmm(value: str) -> time:
    hour, minute = value.split(":")
    return time(int(hour), int(minute))


def in_window(now: datetime, start_str: str, end_str: str) -> bool:
    """True if ``now``'s time is within [start, end] (supports overnight windows)."""
    current = now.time()
    start = _parse_hhmm(start_str)
    end = _parse_hhmm(end_str)
    if start <= end:
        return start <= current <= end
    return current >= start or current <= end


def rotate(account_ids: list[int], last_account_id: int | None) -> list[int]:
    """Round-robin order that does not begin with the last-used account.

    Ensures two consecutive actions do not come from the same account.
    """
    if not account_ids:
        return []
    ordered = sorted(account_ids)
    if last_account_id in ordered and len(ordered) > 1:
        idx = ordered.index(last_account_id)
        ordered = ordered[idx + 1:] + ordered[: idx + 1]
    return ordered
