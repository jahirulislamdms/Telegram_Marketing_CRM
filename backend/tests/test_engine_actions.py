"""Phase 15.1.a — engine target coercion (regression for the send-500 bug).

The 500 on every send was Telethon raising ``ValueError: Cannot find any entity
corresponding to "<numeric id>"`` because a numeric Telegram user id was passed as
a *string* (which Telethon treats as a username lookup). Numeric ids must be ints.
"""

from engine.actions import coerce_target


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
