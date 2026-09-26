import base64
import hashlib
import re
import secrets

PIN_LENGTH = 4
VERIFIER_ALGORITHM = "pbkdf2_sha256"
_PIN_PATTERN = re.compile(r"[0-9]{4}")


def is_valid_pin(pin: str) -> bool:
    return bool(_PIN_PATTERN.fullmatch(pin))


def generate_pin() -> str:
    return "".join(secrets.choice("0123456789") for _ in range(PIN_LENGTH))


def make_pin_verifier(pin: str, salt: str, iterations: int) -> str:
    """`pbkdf2_sha256$<iterations>$<salt>$<base64 hash>`: the counter checks a
    PIN offline with WebCrypto PBKDF2 (SHA-256, 32-byte key, UTF-8 salt)."""
    digest = hashlib.pbkdf2_hmac("sha256", pin.encode(), salt.encode(), iterations, dklen=32)
    encoded = base64.b64encode(digest).decode()
    return f"{VERIFIER_ALGORITHM}${iterations}${salt}${encoded}"


def new_salt() -> str:
    return secrets.token_urlsafe(16)


def verifier_matches(pin: str, verifier: str) -> bool:
    algorithm, iterations, salt, _ = verifier.split("$", 3)
    if algorithm != VERIFIER_ALGORITHM:
        return False
    expected = make_pin_verifier(pin, salt, int(iterations))
    return secrets.compare_digest(expected, verifier)
