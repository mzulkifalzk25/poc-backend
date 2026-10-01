from django.conf import settings
from django.core.mail import send_mail

from apps.accounts.domain.passwords import generate_password
from apps.accounts.domain.role_rules import MANAGER, OWNER
from apps.accounts.models import User
from apps.accounts.repositories.users import UserRepository, user_repository


class NotAStoreLoginError(Exception):
    """Only owners and managers have a password; cashiers sign in another way."""


def set_owner_password(user: User, password: str, users: UserRepository = user_repository) -> None:
    """Stores only the hash of `password`."""
    if user.role not in (OWNER, MANAGER) or user.is_django_admin or not user.email:
        raise NotAStoreLoginError
    user.set_password(password)
    users.save(user, ["password", "updated_at"])


def reset_owner_password(user: User, users: UserRepository = user_repository) -> str:
    """Sets a new random password and returns it once."""
    password = generate_password()
    set_owner_password(user, password, users)
    return password


def send_password_reset_email(user: User, password: str, login_url: str | None = None) -> None:
    body = (
        f"Hello {user.full_name},\n\n"
        "Your MartDesk password has been reset.\n\n"
        f"Sign in here: {login_url or settings.STORE_APP_URL}\n"
        f"Email: {user.email}\n"
        f"Password: {password}\n"
    )
    send_mail("Your MartDesk password was reset", body, None, [user.email], fail_silently=False)
