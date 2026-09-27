def normalize_email(email: str) -> str:
    return email.strip().lower()


def is_django_admin_email(email: str | None, configured: str) -> bool:
    """Only the one maintainer email set on the server may open the Django admin.
    With no email configured, nobody can."""
    return bool(configured.strip()) and normalize_email(email or "") == normalize_email(configured)
