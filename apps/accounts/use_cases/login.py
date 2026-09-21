from django.db.models import Q

from apps.accounts.domain.role_rules import MANAGER, OWNER
from apps.accounts.models import User


class InvalidCredentials(Exception):
    pass


def authenticate_owner_or_manager(login: str, password: str) -> User:
    """Look up an owner or manager by email or username, case-insensitively.

    The contract's `/auth/login` request carries no tenant id (it is public,
    called before any token exists), and email/username are only unique
    *per tenant*, not globally. The POC has no subdomain-style tenant
    routing, so this matches across every tenant and requires exactly one
    hit; ambiguous or absent matches get the same invalid_credentials error
    as a wrong password, same as a role mismatch.
    """
    login = login.strip()
    candidates = list(
        User.objects.filter(
            Q(email__iexact=login) | Q(username__iexact=login),
            role__in=(OWNER, MANAGER),
            is_active=True,
        )
    )
    if len(candidates) != 1:
        raise InvalidCredentials
    user = candidates[0]
    if not user.check_password(password):
        raise InvalidCredentials
    return user
