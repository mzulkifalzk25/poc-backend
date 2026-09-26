import pytest

from apps.tenants.api.throttling import ActivationRateThrottle


@pytest.mark.parametrize(
    ("rate", "expected"),
    [("10/15m", (10, 900)), ("10/m", (10, 60)), ("5/2h", (5, 7200)), ("3/s", (3, 1))],
)
def test_rate_accepts_multi_unit_windows(rate, expected):
    assert ActivationRateThrottle().parse_rate(rate) == expected


def test_bad_rate_is_an_error():
    with pytest.raises(ValueError):
        ActivationRateThrottle().parse_rate("ten per minute")
