import pytest
from django.core.management import CommandError, call_command

from apps.accounts.models import User
from apps.accounts.use_cases.onboard_tenant import NewTenant, TenantSlugTakenError, onboard_tenant
from apps.tenants.models import Tenant, TenantSettings

GETPASS = "apps.accounts.management.commands.create_store_owner.getpass"
PASSWORD = "Blue-Kettle-Morning-42"


def _answers(monkeypatch, *typed: str) -> None:
    replies = iter(typed)
    monkeypatch.setattr(GETPASS, lambda prompt: next(replies))


@pytest.mark.django_db
def test_onboard_tenant_creates_a_tenant_settings_and_owner():
    onboarded = onboard_tenant(
        NewTenant(
            "Fresh Basket Mart",
            "fresh-basket-mart",
            "Sana",
            "Ahmed",
            "sana@example.com",
            password=PASSWORD,
        )
    )
    tenant, owner = onboarded.tenant, onboarded.owner

    assert tenant.slug == "fresh-basket-mart"
    assert TenantSettings.objects.get(tenant=tenant).store_name == "Fresh Basket Mart"
    assert (owner.tenant_id, owner.role, owner.email) == (tenant.id, "owner", "sana@example.com")
    assert owner.full_name == "Sana Ahmed"
    assert owner.check_password(PASSWORD)


@pytest.mark.django_db
def test_a_password_is_generated_when_none_is_given():
    onboarded = onboard_tenant(NewTenant("Mart", "mart", "Sana", "Ahmed", "sana@example.com"))

    assert onboarded.password
    assert onboarded.owner.check_password(onboarded.password)


@pytest.mark.django_db
def test_mart_and_owner_phone_and_address_are_saved():
    onboarded = onboard_tenant(
        NewTenant(
            "Mart",
            "mart",
            "Sana",
            "Ahmed",
            "sana@example.com",
            tenant_phone="0300",
            tenant_address="Main Road",
            owner_phone="0321",
        )
    )

    settings = TenantSettings.objects.get(tenant=onboarded.tenant)
    assert (settings.phone, settings.address) == ("0300", "Main Road")
    assert onboarded.owner.phone == "0321"


@pytest.mark.django_db
def test_a_taken_slug_is_refused():
    Tenant.objects.create(name="Existing", slug="fresh-basket-mart")

    with pytest.raises(TenantSlugTakenError):
        onboard_tenant(
            NewTenant("Fresh Basket Mart", "fresh-basket-mart", "Sana", "Ahmed", "s@example.com")
        )


@pytest.mark.django_db
def test_command_creates_a_tenant_and_owner_who_can_sign_in(monkeypatch):
    _answers(monkeypatch, PASSWORD, PASSWORD)

    call_command(
        "create_store_owner",
        store_name="Fresh Basket Mart",
        owner_first_name="Sana",
        owner_last_name="Ahmed",
        email="sana@example.com",
    )

    owner = User.objects.get(email="sana@example.com")
    assert owner.role == "owner"
    assert owner.check_password(PASSWORD)
    assert Tenant.objects.get(slug="fresh-basket-mart").name == "Fresh Basket Mart"


@pytest.mark.django_db
def test_command_needs_an_email_or_a_username(monkeypatch):
    _answers(monkeypatch, PASSWORD, PASSWORD)

    with pytest.raises(CommandError, match="--email or --username"):
        call_command(
            "create_store_owner",
            store_name="Fresh Basket Mart",
            owner_first_name="Sana",
            owner_last_name="Ahmed",
        )


@pytest.mark.django_db
def test_command_refuses_mismatched_passwords(monkeypatch):
    _answers(monkeypatch, PASSWORD, "different")

    with pytest.raises(CommandError, match="do not match"):
        call_command(
            "create_store_owner",
            store_name="Fresh Basket Mart",
            owner_first_name="Sana",
            owner_last_name="Ahmed",
            email="sana@example.com",
        )

    assert not User.objects.exists()


@pytest.mark.django_db
def test_command_refuses_a_taken_slug(monkeypatch):
    Tenant.objects.create(name="Existing", slug="fresh-basket-mart")
    _answers(monkeypatch, PASSWORD, PASSWORD)

    with pytest.raises(CommandError, match="already exists"):
        call_command(
            "create_store_owner",
            store_name="Fresh Basket Mart",
            owner_first_name="Sana",
            owner_last_name="Ahmed",
            email="sana@example.com",
        )
