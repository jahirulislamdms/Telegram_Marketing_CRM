"""Unit tests for the @SpamBot reply classifier (pure logic)."""

import pytest

from engine.health import (
    SPAM_BANNED,
    SPAM_CLEAN,
    SPAM_LIMITED,
    SPAM_UNKNOWN,
    classify_spambot_reply,
)


@pytest.mark.parametrize(
    "text",
    [
        "Good news, no limits are currently applied to your account. 🎉",
        "Good news, no limits are currently applied to your account. You're free as a bird!",
    ],
)
def test_clean(text):
    assert classify_spambot_reply(text) == SPAM_CLEAN


@pytest.mark.parametrize(
    "text",
    [
        "I'm afraid your account is now limited until 25 Jul 2026.",
        "Unfortunately, some Telegram features are unavailable to you.",
        "Some Telegram users flagged your messages as spam.",
    ],
)
def test_limited(text):
    assert classify_spambot_reply(text) == SPAM_LIMITED


def test_banned():
    text = (
        "Unfortunately, your account was blocked for violations of the "
        "Telegram Terms of Service."
    )
    assert classify_spambot_reply(text) == SPAM_BANNED


@pytest.mark.parametrize("text", ["", "hello there", "unrelated message"])
def test_unknown(text):
    assert classify_spambot_reply(text) == SPAM_UNKNOWN
