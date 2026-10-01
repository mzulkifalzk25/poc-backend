import pytest
from django.core import mail
from django.test import Client
from django.urls import reverse

from apps.accounts.models import User
from apps.accounts.use_cases.django_admin import save_django_admin
from apps.tenants.models import Tenant

ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "Blue-Kettle-Morning-42"
URL = "admin:tenants_tenant_onboard"


@pytest.fixture(autouse=True)
def _settings(settings):
    settings.DJANGO_ADMIN_EMAIL = ADMIN_EMAIL
    settings.STORE_APP_URL = "https://pos.example.com/"


@pytest.fixture
def signed_in(db) -> Client:
    save_django_admin(ADMIN_EMAIL, ADMIN_PASSWORD)
    client = Client()
    client.post(reverse("admin:login"), {"username": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    return client


def _form(**changes) -> dict:
    form = {
        "store_name": "Al Madina Mart",
        "owner_first_name": "Ahmed",
        "owner_last_name": "Khan",
        "owner_email": "ahmed@example.com",
    }
    return {**form, **changes}


def test_the_page_needs_the_django_admin():
    response = Client().get(reverse(URL))

    assert response.status_code == 302
    assert "login" in response["Location"]


def test_the_add_button_opens_the_onboarding_page(signed_in):
    response = signed_in.get(reverse("admin:tenants_tenant_add"))

    assert response["Location"] == reverse(URL)
    assert signed_in.get(reverse(URL)).status_code == 200


def test_creating_a_mart_emails_the_owner_the_login(signed_in):
    response = signed_in.post(reverse(URL), _form(password="Green-Lantern-River-77"))

    assert response.status_code == 302
    tenant = Tenant.objects.get(slug="al-madina-mart")
    owner = User.objects.get(email="ahmed@example.com")
    assert (owner.tenant_id, owner.role, owner.full_name) == (tenant.id, "owner", "Ahmed Khan")
    assert owner.check_password("Green-Lantern-River-77")
    (sent,) = mail.outbox
    assert sent.to == ["ahmed@example.com"]
    assert "https://pos.example.com/" in sent.body
    assert "Green-Lantern-River-77" in sent.body


def test_an_empty_password_is_generated_and_emailed(signed_in):
    signed_in.post(reverse(URL), _form())

    owner = User.objects.get(email="ahmed@example.com")
    password = next(
        line.removeprefix("Password: ")
        for line in mail.outbox[0].body.splitlines()
        if line.startswith("Password: ")
    )
    assert owner.check_password(password)


def test_a_failed_email_still_creates_the_mart_and_shows_the_password(signed_in, monkeypatch):
    def fail(*args, **kwargs):
        raise OSError("smtp down")

    monkeypatch.setattr("apps.accounts.use_cases.send_owner_welcome.send_mail", fail)

    response = signed_in.post(reverse(URL), _form(), follow=True)

    assert Tenant.objects.filter(slug="al-madina-mart").exists()
    assert "could not be sent" in response.content.decode()


def test_a_taken_mart_name_is_refused(signed_in):
    Tenant.objects.create(name="Other", slug="al-madina-mart")

    response = signed_in.post(reverse(URL), _form())

    assert "already exists" in response.content.decode()
    assert not User.objects.filter(email="ahmed@example.com").exists()


def test_an_email_already_used_by_an_owner_is_refused(signed_in):
    signed_in.post(reverse(URL), _form())

    response = signed_in.post(reverse(URL), _form(store_name="Second Mart"))

    assert "already signs in" in response.content.decode()
    assert Tenant.objects.filter(slug="second-mart").count() == 0


def test_a_weak_password_is_refused(signed_in):
    response = signed_in.post(reverse(URL), _form(password="123"))

    assert response.status_code == 200
    assert not Tenant.objects.filter(slug="al-madina-mart").exists()


def test_the_admin_home_links_to_the_onboarding_page(signed_in):
    page = signed_in.get(reverse("admin:index"))

    assert reverse(URL) in page.content.decode()
