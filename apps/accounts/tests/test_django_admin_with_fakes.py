from types import SimpleNamespace

from apps.accounts.domain.django_admin import is_django_admin_email
from apps.accounts.use_cases.django_admin import (
    MAINTENANCE_TENANT_SLUG,
    authenticate_django_admin,
    django_admin_by_id,
    save_django_admin,
)

ADMIN = "admin@example.com"


class FakeUsers:
    def __init__(self) -> None:
        self.by_email: dict = {}

    def django_admin(self, email: str):
        return self.by_email.get(email.strip().lower())

    def django_admin_by_id(self, user_id: int):
        return next((u for u in self.by_email.values() if u.id == user_id), None)

    def save(self, user, fields=None) -> None:
        user.id = user.id or len(self.by_email) + 1
        self.by_email[user.email] = user


class FakeTenants:
    def __init__(self) -> None:
        self.slugs: list[str] = []

    def get_or_create(self, slug: str, name: str):
        self.slugs.append(slug)
        return SimpleNamespace(id=99)


def _with_admin(password: str = "s3cret-pass!") -> FakeUsers:
    users = FakeUsers()
    save_django_admin(ADMIN, password, users, FakeTenants())
    return users


def test_only_the_configured_email_is_the_django_admin():
    assert is_django_admin_email(" Admin@Example.com ", ADMIN)
    assert not is_django_admin_email("owner@shop.com", ADMIN)
    assert not is_django_admin_email(ADMIN, "  ")
    assert not is_django_admin_email(None, ADMIN)


def test_creates_the_admin_in_the_maintenance_tenant():
    users, tenants = FakeUsers(), FakeTenants()

    created = save_django_admin(" Admin@Example.com ", "s3cret-pass!", users, tenants)

    user = users.django_admin(ADMIN)
    assert created is True
    assert tenants.slugs == [MAINTENANCE_TENANT_SLUG]
    assert (user.tenant_id, user.email, user.is_django_admin) == (99, ADMIN, True)
    assert user.check_password("s3cret-pass!")


def test_a_second_run_resets_the_password_and_reactivates():
    users = _with_admin("first-pass!")
    users.django_admin(ADMIN).is_active = False

    created = save_django_admin(ADMIN, "second-pass!", users, FakeTenants())

    user = users.django_admin(ADMIN)
    assert created is False
    assert user.is_active and user.check_password("second-pass!")


def test_signs_in_only_with_the_configured_email_and_right_password():
    users = _with_admin()

    assert authenticate_django_admin("ADMIN@example.com", "s3cret-pass!", ADMIN, users)
    assert authenticate_django_admin(ADMIN, "wrong", ADMIN, users) is None
    assert authenticate_django_admin(ADMIN, "s3cret-pass!", "other@example.com", users) is None


def test_a_deactivated_admin_cannot_sign_in():
    users = _with_admin()
    users.django_admin(ADMIN).is_active = False

    assert authenticate_django_admin(ADMIN, "s3cret-pass!", ADMIN, users) is None


def test_a_session_ends_when_the_configured_email_changes():
    users = _with_admin()
    admin_id = users.django_admin(ADMIN).id

    assert django_admin_by_id(admin_id, ADMIN, users) is not None
    assert django_admin_by_id(admin_id, "new@example.com", users) is None
