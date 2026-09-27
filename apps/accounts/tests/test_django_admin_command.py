import pytest
from django.contrib.auth import authenticate
from django.core.management import CommandError, call_command

from apps.accounts.models import User
from apps.accounts.use_cases.django_admin import MAINTENANCE_TENANT_SLUG
from apps.tenants.models import Tenant

GETPASS = "apps.accounts.management.commands.create_django_admin.getpass"
ADMIN = "admin@example.com"
PASSWORD = "Blue-Kettle-Morning-42"


@pytest.fixture(autouse=True)
def _admin_email(settings):
    settings.DJANGO_ADMIN_EMAIL = ADMIN


def _answers(monkeypatch, *typed: str) -> None:
    replies = iter(typed)
    monkeypatch.setattr(GETPASS, lambda prompt: next(replies))


@pytest.mark.django_db
def test_creates_the_configured_admin_who_can_then_sign_in(monkeypatch):
    _answers(monkeypatch, PASSWORD, PASSWORD)

    call_command("create_django_admin")

    admin = User.objects.get(is_django_admin=True)
    assert admin.email == ADMIN
    assert Tenant.objects.get(id=admin.tenant_id).slug == MAINTENANCE_TENANT_SLUG
    assert authenticate(username="ADMIN@example.com", password=PASSWORD) == admin
    assert authenticate(username=ADMIN, password="wrong") is None


@pytest.mark.django_db
def test_running_again_resets_the_password_without_a_second_account(monkeypatch):
    _answers(monkeypatch, PASSWORD, PASSWORD, "Green-Lamp-Evening-77", "Green-Lamp-Evening-77")
    call_command("create_django_admin")

    call_command("create_django_admin")

    assert User.objects.filter(is_django_admin=True).count() == 1
    assert authenticate(username=ADMIN, password="Green-Lamp-Evening-77")


@pytest.mark.django_db
def test_refuses_to_run_without_a_configured_email(monkeypatch, settings):
    settings.DJANGO_ADMIN_EMAIL = ""
    _answers(monkeypatch, PASSWORD, PASSWORD)

    with pytest.raises(CommandError, match="DJANGO_ADMIN_EMAIL"):
        call_command("create_django_admin")

    assert not User.objects.filter(is_django_admin=True).exists()


@pytest.mark.parametrize(
    ("typed", "message"),
    [((PASSWORD, "different"), "do not match"), (("12345", "12345"), "too short")],
)
@pytest.mark.django_db
def test_refuses_bad_passwords_and_creates_nothing(monkeypatch, typed, message):
    _answers(monkeypatch, *typed)

    with pytest.raises(CommandError, match=message):
        call_command("create_django_admin")

    assert not User.objects.filter(is_django_admin=True).exists()


@pytest.mark.django_db
def test_a_store_owner_password_never_signs_in_to_the_admin():
    owner = User(tenant_id=1, full_name="Sana Ahmed", role="owner", email="sana@example.com")
    owner.set_password(PASSWORD)
    owner.save()

    assert authenticate(username="sana@example.com", password=PASSWORD) is None


@pytest.mark.django_db
def test_a_flagged_account_with_another_email_is_refused():
    other = User(tenant_id=1, full_name="Other", role="owner", email="other@example.com")
    other.is_django_admin = True
    other.set_password(PASSWORD)
    other.save()

    assert authenticate(username="other@example.com", password=PASSWORD) is None
    assert not other.is_staff
