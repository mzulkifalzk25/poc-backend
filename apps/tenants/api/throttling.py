import re

from rest_framework.request import Request
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import APIView

_RATE = re.compile(r"(\d+)/(\d*)([smhd])")
_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400}


class ActivationRateThrottle(SimpleRateThrottle):
    """Per IP. Accepts multi-unit windows such as `10/15m`, which DRF's own
    parser reads as `10/m`."""

    scope = "activation"

    def parse_rate(self, rate: str | None) -> tuple[int | None, int | None]:
        if rate is None:
            return None, None
        match = _RATE.fullmatch(rate)
        if match is None:
            raise ValueError(f"Bad throttle rate: {rate}")
        count, units, unit = match.groups()
        return int(count), int(units or 1) * _SECONDS[unit]

    def get_cache_key(self, request: Request, view: APIView) -> str:
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}
