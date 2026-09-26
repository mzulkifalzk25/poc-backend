from datetime import UTC, datetime, timedelta

import pytest

from apps.tenants.domain.activation_code import (
    ALPHABET,
    CodeExpiredError,
    CodeInvalidError,
    CodeUsedError,
    ensure_code_usable,
    expiry_for,
    format_code,
    generate_code,
    hash_code,
    normalize_code,
)

NOW = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)


def test_generated_code_is_eight_characters_from_the_alphabet():
    for _ in range(200):
        code = generate_code()
        assert len(code) == 8
        assert set(code) <= set(ALPHABET)


def test_alphabet_leaves_out_look_alike_characters():
    for char in "0O1IL":
        assert char not in ALPHABET


def test_code_is_shown_with_a_hyphen_in_the_middle():
    assert format_code("K7M4Q92R") == "K7M4-Q92R"


@pytest.mark.parametrize("raw", ["K7M4-Q92R", "k7m4-q92r", "k7m4q92r", " K7M4 Q92R "])
def test_case_hyphens_and_spaces_are_ignored(raw):
    assert normalize_code(raw) == "K7M4Q92R"


@pytest.mark.parametrize("raw", ["", "K7M4-Q92", "K7M4-Q92RX", "K7M0-Q92R", "K7M4_Q92R"])
def test_text_that_cannot_be_a_code_normalizes_to_none(raw):
    assert normalize_code(raw) is None


def test_hash_is_stable_and_depends_on_the_key():
    assert hash_code("K7M4Q92R", "key-a") == hash_code("K7M4Q92R", "key-a")
    assert hash_code("K7M4Q92R", "key-a") != hash_code("K7M4Q92R", "key-b")
    assert "K7M4Q92R" not in hash_code("K7M4Q92R", "key-a")


def test_code_lives_fifteen_minutes():
    assert expiry_for(NOW) == NOW + timedelta(minutes=15)


def test_fresh_unused_code_is_usable():
    ensure_code_usable(expiry_for(NOW), used_at=None, revoked_at=None, now=NOW)


def test_code_is_expired_at_its_expiry_time():
    with pytest.raises(CodeExpiredError):
        ensure_code_usable(NOW, used_at=None, revoked_at=None, now=NOW)


def test_used_code_is_reported_as_used_even_after_expiry():
    with pytest.raises(CodeUsedError):
        ensure_code_usable(NOW - timedelta(minutes=1), used_at=NOW, revoked_at=None, now=NOW)


def test_revoked_code_is_invalid():
    with pytest.raises(CodeInvalidError):
        ensure_code_usable(expiry_for(NOW), used_at=None, revoked_at=NOW, now=NOW)
