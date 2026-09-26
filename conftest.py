import pytest


@pytest.fixture(autouse=True)
def _fast_pin_verifier(settings):
    settings.PIN_VERIFIER_ITERATIONS = 1000
