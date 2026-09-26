from decimal import Decimal

import pytest

from apps.tenants.domain.settings_rules import is_valid_tax_rate


@pytest.mark.parametrize("rate", ["0", "0.00", "5.00", "17.00", "17.50", "100", "100.00"])
def test_percent_from_zero_to_one_hundred_is_valid(rate):
    assert is_valid_tax_rate(Decimal(rate))


@pytest.mark.parametrize("rate", ["-0.01", "-5", "100.01", "150.00", "999.99"])
def test_rates_outside_zero_to_one_hundred_are_invalid(rate):
    assert not is_valid_tax_rate(Decimal(rate))
