"""Engine target coercion + phone resolution (regressions for the send-500 bugs).

- 15.1.a: a numeric Telegram user id passed as a *string* was misread as a
  username lookup. Numeric ids must be ints.
- phone fix: a phone number can't be messaged directly — it must be imported to
  resolve it to a user first, and any send failure must return cleanly (no 500).
"""

from types import SimpleNamespace

import pytest

from engine.actions import coerce_target, resolve_for_send, send_dm, send_media


class _FakeClient:
    """Mimics the bits of a Telethon client the send path uses.

    ``send_message``/``send_file`` reject a raw '+phone' string the way real
    Telethon does; calling the client with an ImportContactsRequest returns the
    configured user (or none), which is how a phone is resolved to an entity.
    """

    def __init__(self, phone_user=None, fail: bool = False):
        self.phone_user = phone_user
        self.fail = fail
        self.sent: list = []

    async def __call__(self, request):  # ImportContactsRequest
        return SimpleNamespace(users=[self.phone_user] if self.phone_user else [])

    async def _guard(self, entity):
        if self.fail:
            raise ValueError("Could not find the input entity for PeerUser")
        if isinstance(entity, str) and entity.startswith("+"):
            raise ValueError("Could not find the input entity for a raw phone")

    async def send_message(self, entity, text):
        await self._guard(entity)
        self.sent.append((entity, text))
        return SimpleNamespace(id=555)

    async def send_file(self, entity, file, **kw):
        await self._guard(entity)
        self.sent.append((entity, file))
        return SimpleNamespace(id=556)


def test_numeric_string_id_becomes_int():
    # The exact shape that caused the 500 in production.
    assert coerce_target("6430475606") == 6430475606
    assert isinstance(coerce_target("6430475606"), int)


def test_negative_chat_id_becomes_int():
    assert coerce_target("-1001234567890") == -1001234567890


def test_username_and_phone_stay_strings():
    assert coerce_target("@someone") == "@someone"
    assert coerce_target("+8801646562266") == "+8801646562266"
    assert coerce_target("plainusername") == "plainusername"


def test_int_and_nonstring_pass_through():
    assert coerce_target(6430475606) == 6430475606
    obj = object()
    assert coerce_target(obj) is obj


def test_whitespace_and_empty():
    assert coerce_target("  6430475606  ") == 6430475606
    assert coerce_target("") == ""


# ---------------------------------------------- phone-send fix (regression) ---


async def test_send_dm_to_phone_imports_then_sends_to_user():
    """A '+phone' target is resolved to a user (import) before sending."""
    user = SimpleNamespace(id=8801)
    client = _FakeClient(phone_user=user)
    result = await send_dm(client, "+8801646562267", "hi")
    assert result == {"sent": True}
    # It sent to the resolved user entity, not the raw phone string.
    assert client.sent == [(user, "hi")]


async def test_send_dm_to_phone_without_telegram_returns_clean_error():
    client = _FakeClient(phone_user=None)  # phone has no Telegram account
    result = await send_dm(client, "+123456789", "hi")
    assert result["sent"] is False
    assert "no Telegram account" in result["error"]
    assert client.sent == []


async def test_send_dm_generic_failure_never_raises():
    """Any send failure returns cleanly so the engine never 500s."""
    client = _FakeClient(fail=True)
    result = await send_dm(client, 999, "hi")  # a numeric id that can't be found
    assert result["sent"] is False and result["error"]


async def test_send_dm_numeric_id_passes_through():
    client = _FakeClient()
    result = await send_dm(client, "555", "hi")  # resolved contact -> int id
    assert result == {"sent": True}
    assert client.sent == [(555, "hi")]


async def test_send_media_resolves_phone():
    user = SimpleNamespace(id=42)
    client = _FakeClient(phone_user=user)
    result = await send_media(client, "+8801646562267", b"bytes", "p.jpg", "image/jpeg", "image", "cap")
    assert result["sent"] is True and result["message_id"] == 556
    assert client.sent[0][0] is user


async def test_resolve_for_send_passthrough():
    client = _FakeClient()
    assert await resolve_for_send(client, 12345) == 12345  # int id
    assert await resolve_for_send(client, "@someone") == "@someone"  # username
