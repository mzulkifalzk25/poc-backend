import pytest

from apps.accounts.domain.pin import (
    generate_pin,
    is_valid_pin,
    make_pin_verifier,
    new_salt,
    verifier_matches,
)


@pytest.mark.parametrize("pin", ["0000", "1234", "9999"])
def test_four_digits_are_a_valid_pin(pin):
    assert is_valid_pin(pin)


@pytest.mark.parametrize("pin", ["", "123", "12345", "12a4", " 123", "١٢٣٤"])
def test_anything_else_is_not_a_pin(pin):
    assert not is_valid_pin(pin)


def test_generated_pins_are_four_digits():
    assert all(is_valid_pin(generate_pin()) for _ in range(100))


def test_verifier_matches_the_published_pbkdf2_sha256_vector():
    # RFC 7914 section 11: P="passwd", S="salt", c=1 (first 32 bytes).
    verifier = make_pin_verifier("passwd", "salt", 1)

    assert verifier == "pbkdf2_sha256$1$salt$VawEblbjCJ/sFpHCJUS2BflBhSFt3gRl5oudV8INrLw="


def test_verifier_checks_the_right_pin_only():
    verifier = make_pin_verifier("4821", new_salt(), 1000)

    assert verifier_matches("4821", verifier)
    assert not verifier_matches("4822", verifier)


def test_each_verifier_gets_its_own_salt():
    assert make_pin_verifier("4821", new_salt(), 1000) != make_pin_verifier(
        "4821", new_salt(), 1000
    )
