from collections.abc import Iterable

from apps.accounts.models import User
from apps.accounts.repositories.users import UserRepository, user_repository


class InvalidCredentials(Exception):
    """`user` is the single matching account when there is one (wrong
    password), so the failure can be logged against its tenant."""

    def __init__(self, user: User | None = None):
        super().__init__()
        self.user = user


def authenticate_account(
    login: str, password: str, roles: Iterable[str], users: UserRepository = user_repository
) -> User:
    """Look up an active account with one of `roles` by email or username,
    case-insensitively.

    Login carries no tenant id (it is called before any token exists), and
    email/username are only unique *per tenant*, not globally. The POC has
    no subdomain-style tenant routing, so this matches across every tenant
    and requires exactly one hit; ambiguous or absent matches get the same
    invalid_credentials error as a wrong password, same as a role mismatch.
    """
    user = find_login_account(login, roles, users)
    if user is None:
        raise InvalidCredentials
    if not user.check_password(password):
        raise InvalidCredentials(user)
    return user


def find_login_account(
    login: str, roles: Iterable[str], users: UserRepository = user_repository
) -> User | None:
    candidates = users.login_candidates(login, roles)
    return candidates[0] if len(candidates) == 1 else None
