from django.conf import settings

from apps.accounts.models import User
from apps.accounts.use_cases.django_admin import authenticate_django_admin, django_admin_by_id


class DjangoAdminBackend:
    """The only Django authentication backend: it signs in to the Django admin,
    and only the one account whose email is `DJANGO_ADMIN_EMAIL`.

    Store owners and cashiers never use Django sessions; they sign in to the
    store app through the API with tokens, so their passwords never open the admin."""

    def authenticate(
        self, request, username: str | None = None, password: str | None = None, **kwargs
    ) -> User | None:
        if not username or not password:
            return None
        return authenticate_django_admin(username, password, settings.DJANGO_ADMIN_EMAIL)

    def get_user(self, user_id: int) -> User | None:
        return django_admin_by_id(user_id, settings.DJANGO_ADMIN_EMAIL)
