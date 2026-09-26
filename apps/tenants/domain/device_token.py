import hashlib
import secrets

TOKEN_BYTES = 32


def generate_device_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


def hash_device_token(token: str) -> str:
    """The token is long and random, so a plain SHA-256 is enough."""
    return hashlib.sha256(token.encode()).hexdigest()
