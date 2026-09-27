import secrets


def generate_password() -> str:
    """Shown once, in a reset-password dialog. Random and URL-safe."""
    return secrets.token_urlsafe(9)
