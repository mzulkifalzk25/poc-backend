from types import SimpleNamespace

from apps.accounts.use_cases.platform_admin import (
    PLATFORM_TENANT_SLUG,
    authenticate_platform_admin,
    save_platform_admin,
)


class FakeUsers:
    def __init__(self) -> None:
        self.by_email: dict = {}

    def platform_admin(self, email: str):
        return self.by_email.get(email.strip().lower())

    def save(self, user, fields=None) -> None:
        self.by_email[user.email] = user


class FakeTenants:
    def __init__(self) -> None:
        self.slugs: list[str] = []

    def get_or_create(self, slug: str, name: str):
        self.slugs.append(slug)
        return SimpleNamespace(id=99)


def test_creates_the_admin_in_the_platform_tenant():
    users, tenants = FakeUsers(), FakeTenants()

    created = save_platform_admin(" Admin@Example.com ", "s3cret-pass!", users, tenants)

    user = users.platform_admin("admin@example.com")
    assert created is True
    assert tenants.slugs == [PLATFORM_TENANT_SLUG]
    assert (user.tenant_id, user.email, user.is_platform_admin) == (99, "admin@example.com", True)
    assert user.check_password("s3cret-pass!")


def test_a_second_run_resets_the_password_and_reactivates():
    users, tenants = FakeUsers(), FakeTenants()
    save_platform_admin("admin@example.com", "first-pass!", users, tenants)
    users.platform_admin("admin@example.com").is_active = False

    created = save_platform_admin("admin@example.com", "second-pass!", users, tenants)

    user = users.platform_admin("admin@example.com")
    assert created is False
    assert user.is_active and user.check_password("second-pass!")
    assert not user.check_password("first-pass!")


def test_signs_in_only_with_the_right_email_and_password():
    users = FakeUsers()
    save_platform_admin("admin@example.com", "s3cret-pass!", users, FakeTenants())

    assert authenticate_platform_admin("ADMIN@example.com", "s3cret-pass!", users) is not None
    assert authenticate_platform_admin("admin@example.com", "wrong", users) is None
    assert authenticate_platform_admin("other@example.com", "s3cret-pass!", users) is None


def test_a_deactivated_admin_cannot_sign_in():
    users = FakeUsers()
    save_platform_admin("admin@example.com", "s3cret-pass!", users, FakeTenants())
    users.platform_admin("admin@example.com").is_active = False

    assert authenticate_platform_admin("admin@example.com", "s3cret-pass!", users) is None
