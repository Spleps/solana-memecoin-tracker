import pytest

from bot.validation import is_solana_address, parse_allowed_chat_ids


def test_solana_address_validation() -> None:
    assert is_solana_address("11111111111111111111111111111111")
    assert not is_solana_address("not-an-address")
    assert not is_solana_address("0" * 32)


def test_allowed_chat_ids() -> None:
    assert parse_allowed_chat_ids("1, -2") == frozenset({1, -2})
    assert parse_allowed_chat_ids("") == frozenset()


def test_invalid_allowed_chat_id() -> None:
    with pytest.raises(ValueError):
        parse_allowed_chat_ids("abc")
