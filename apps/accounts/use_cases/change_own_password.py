from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.accounts.models import User
from apps.accounts.repositories.users import UserRepository, user_repository
from apps.audit.use_cases.record_activity import ActivityEntry, record_activity


class WrongCurrentPasswordError(Exception):
    pass


class WeakPasswordError(Exception):
    def __init__(self, messages: list[str]):
        super().__init__()
        self.messages = messages


def change_own_password(
    user: User, current: str, new: str, users: UserRepository = user_repository
) -> None:
    if not user.check_password(current):
        raise WrongCurrentPasswordError
    try:
        validate_password(new, user)
    except ValidationError as error:
        raise WeakPasswordError(list(error.messages)) from None
    user.set_password(new)
    with transaction.atomic():
        users.save(user, ["password", "updated_at"])
        record_activity(
            ActivityEntry(
                tenant_id=user.tenant_id,
                user_id=user.id,
                action="password_changed",
                entity_type="user",
                entity_id=str(user.id),
            )
        )
