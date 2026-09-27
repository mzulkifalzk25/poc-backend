from apps.accounts.models import User
from apps.accounts.use_cases.platform_admin import (
    authenticate_platform_admin,
    platform_admin_by_id,
)


class PlatformAdminBackend:
    """The only Django authentication backend: it signs in to the Django admin.

    Store staff never use Django sessions; they sign in through the API with
    tokens. So an owner's or cashier's password never opens the admin."""

    def authenticate(
        self, request, username: str | None = None, password: str | None = None, **kwargs
    ) -> User | None:
        if not username or not password:
            return None
        return authenticate_platform_admin(username, password)

    def get_user(self, user_id: int) -> User | None:
        return platform_admin_by_id(user_id)
