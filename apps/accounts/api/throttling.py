import hashlib

from rest_framework.request import Request
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import APIView


class LoginRateThrottle(SimpleRateThrottle):
    """Throttles by IP *and* the attempted login, per the contract, without
    ever locking the account itself out."""

    scope = "login"

    def get_cache_key(self, request: Request, view: APIView) -> str:
        login = str(request.data.get("login", "")).strip().lower()
        login_hash = hashlib.sha256(login.encode()).hexdigest()
        ident = f"{self.get_ident(request)}:{login_hash}"
        return self.cache_format % {"scope": self.scope, "ident": ident}
