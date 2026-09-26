import hashlib
import hmac
import secrets
from datetime import datetime, timedelta

# Uppercase letters and digits without the look-alikes 0, O, 1, I and L.
ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
CODE_LENGTH = 8
CODE_LIFETIME = timedelta(minutes=15)


class CodeInvalidError(Exception):
    pass


class CodeExpiredError(Exception):
    pass


class CodeUsedError(Exception):
    pass


def generate_code() -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(CODE_LENGTH))


def format_code(code: str) -> str:
    """`K7M4Q92R` is shown as `K7M4-Q92R`."""
    half = CODE_LENGTH // 2
    return f"{code[:half]}-{code[half:]}"


def normalize_code(raw: str) -> str | None:
    """Case, hyphens and spaces are ignored on entry. Returns None when the
    rest cannot be a code at all."""
    code = raw.replace("-", "").replace(" ", "").upper()
    if len(code) != CODE_LENGTH or any(char not in ALPHABET for char in code):
        return None
    return code


def hash_code(code: str, key: str) -> str:
    """Keyed hash, so a leaked table cannot be brute-forced without the key."""
    return hmac.new(key.encode(), code.encode(), hashlib.sha256).hexdigest()


def expiry_for(issued_at: datetime) -> datetime:
    return issued_at + CODE_LIFETIME


def ensure_code_usable(
    expires_at: datetime,
    used_at: datetime | None,
    revoked_at: datetime | None,
    now: datetime,
) -> None:
    if revoked_at is not None:
        raise CodeInvalidError
    if used_at is not None:
        raise CodeUsedError
    if now >= expires_at:
        raise CodeExpiredError
