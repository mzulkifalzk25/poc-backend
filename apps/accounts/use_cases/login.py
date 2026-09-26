from django.db.models import Q

from apps.accounts.domain.role_rules import MANAGER, OWNER
from apps.accounts.models import User


class InvalidCredentials(Exception):
    """`user` is the single matching account when there is one (wrong
    password), so the failure can be logged against its tenant."""

    def __init__(self, user: User | None = None):
        super().__init__()
        self.user = user


def authenticate_owner_or_manager(login: str, password: str) -> User:
    """Look up an owner or manager by email or username, case-insensitively.

    The contract's `/auth/login` request carries no tenant id (it is public,
    called before any token exists), and email/username are only unique
    *per tenant*, not globally. The POC has no subdomain-style tenant
    routing, so this matches across every tenant and requires exactly one
    hit; ambiguous or absent matches get the same invalid_credentials error
    as a wrong password, same as a role mismatch.
    """
    user = find_login_account(login)
    if user is None:
        raise InvalidCredentials
    if not user.check_password(password):
        raise InvalidCredentials(user)
    return user


def find_login_account(login: str) -> User | None:
    candidates = list(
        User.objects.filter(
            Q(email__iexact=login.strip()) | Q(username__iexact=login.strip()),
            role__in=(OWNER, MANAGER),
            is_active=True,
        )[:2]
    )
    return candidates[0] if len(candidates) == 1 else None
