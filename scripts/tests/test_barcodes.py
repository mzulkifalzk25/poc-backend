import pytest

from scripts.seed.barcodes import ean13_check_digit, is_valid_ean13, sample_barcode


def test_check_digit_matches_a_known_ean13():
    assert ean13_check_digit("400638133393") == "1"


def test_sample_barcodes_are_13_digit_896_and_valid():
    barcode = sample_barcode(7)

    assert barcode.startswith("896000000007")
    assert len(barcode) == 13
    assert is_valid_ean13(barcode)


def test_sample_barcodes_are_unique_per_sequence():
    assert len({sample_barcode(sequence) for sequence in range(1, 20_000)}) == 19_999


@pytest.mark.parametrize("barcode", ["8960000000070", "896000000007", "89600000000٧1", "abc"])
def test_rejects_bad_barcodes(barcode):
    assert not is_valid_ean13(barcode)


@pytest.mark.parametrize("body", ["12345", "89600000000a", "89600000000٧"])
def test_check_digit_needs_twelve_ascii_digits(body):
    with pytest.raises(ValueError):
        ean13_check_digit(body)
