import pytest
from django.contrib.auth import authenticate
from django.core.management import CommandError, call_command

from apps.accounts.models import User
from apps.accounts.use_cases.platform_admin import PLATFORM_TENANT_SLUG
from apps.tenants.models import Tenant

COMMAND = "apps.accounts.management.commands.create_platform_admin.getpass"
PASSWORD = "Blue-Kettle-Morning-42"


def _answers(monkeypatch, *typed: str) -> None:
    replies = iter(typed)
    monkeypatch.setattr(COMMAND, lambda prompt: next(replies))


@pytest.mark.django_db
def test_creates_the_admin_who_can_then_sign_in(monkeypatch):
    _answers(monkeypatch, PASSWORD, PASSWORD)

    call_command("create_platform_admin", "--email", "Admin@Example.com")

    admin = User.objects.get(is_platform_admin=True)
    assert admin.email == "admin@example.com"
    assert Tenant.objects.get(id=admin.tenant_id).slug == PLATFORM_TENANT_SLUG
    assert authenticate(username="ADMIN@example.com", password=PASSWORD) == admin
    assert authenticate(username="admin@example.com", password="wrong") is None


@pytest.mark.django_db
def test_running_again_resets_the_password_without_a_second_account(monkeypatch):
    _answers(monkeypatch, PASSWORD, PASSWORD, "Green-Lamp-Evening-77", "Green-Lamp-Evening-77")
    call_command("create_platform_admin", "--email", "admin@example.com")

    call_command("create_platform_admin", "--email", "admin@example.com")

    assert User.objects.filter(is_platform_admin=True).count() == 1
    assert authenticate(username="admin@example.com", password="Green-Lamp-Evening-77")


@pytest.mark.parametrize(
    ("email", "typed", "message"),
    [
        ("not-an-email", (PASSWORD, PASSWORD), "valid email"),
        ("admin@example.com", (PASSWORD, "different"), "do not match"),
        ("admin@example.com", ("12345", "12345"), "too short"),
    ],
)
@pytest.mark.django_db
def test_refuses_bad_input_and_creates_nothing(monkeypatch, email, typed, message):
    _answers(monkeypatch, *typed)

    with pytest.raises(CommandError, match=message):
        call_command("create_platform_admin", "--email", email)

    assert not User.objects.filter(is_platform_admin=True).exists()


@pytest.mark.django_db
def test_a_store_owner_password_never_signs_in_to_the_admin():
    owner = User(tenant_id=1, full_name="Sana Ahmed", role="owner", email="sana@example.com")
    owner.set_password(PASSWORD)
    owner.save()

    assert authenticate(username="sana@example.com", password=PASSWORD) is None
