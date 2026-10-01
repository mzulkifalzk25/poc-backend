import pytest
from django.core import mail
from django.test import Client
from django.urls import reverse

from apps.accounts.models import User
from apps.accounts.use_cases.django_admin import save_django_admin

ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "Blue-Kettle-Morning-42"
ACTION = {"action": "reset_password_and_email"}


@pytest.fixture(autouse=True)
def _settings(settings):
    settings.DJANGO_ADMIN_EMAIL = ADMIN_EMAIL


@pytest.fixture
def signed_in(db) -> Client:
    save_django_admin(ADMIN_EMAIL, ADMIN_PASSWORD)
    client = Client()
    client.post(reverse("admin:login"), {"username": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    return client


def _user(role: str, email: str | None, name: str) -> User:
    user = User(tenant_id=1, full_name=name, role=role, email=email)
    user.set_password("old-Password-1")
    user.save()
    return user


def _run(client: Client, *users: User):
    data = {**ACTION, "_selected_action": [u.pk for u in users]}
    return client.post(reverse("admin:accounts_user_changelist"), data, follow=True)


def test_an_owner_gets_a_new_password_by_email(signed_in):
    owner = _user("owner", "sana@example.com", "Sana Ahmed")

    _run(signed_in, owner)

    owner.refresh_from_db()
    (sent,) = mail.outbox
    password = next(
        line.removeprefix("Password: ")
        for line in sent.body.splitlines()
        if line.startswith("Password: ")
    )
    assert sent.to == ["sana@example.com"]
    assert owner.check_password(password)
    assert not owner.check_password("old-Password-1")


def test_a_cashier_is_not_reset(signed_in):
    cashier = _user("cashier", None, "Bilal Raza")

    response = _run(signed_in, cashier)

    cashier.refresh_from_db()
    assert cashier.check_password("old-Password-1")
    assert not mail.outbox
    assert "only owners and managers" in response.content.decode()


def test_a_failed_email_shows_the_new_password(signed_in, monkeypatch):
    owner = _user("owner", "sana@example.com", "Sana Ahmed")

    def fail(*args, **kwargs):
        raise OSError("smtp down")

    monkeypatch.setattr("apps.accounts.use_cases.reset_owner_password.send_mail", fail)

    response = _run(signed_in, owner)

    owner.refresh_from_db()
    assert "could not be sent" in response.content.decode()
    assert not owner.check_password("old-Password-1")


def _set_url(user: User) -> str:
    return reverse("admin:accounts_user_set_password", args=[user.pk])


def test_the_change_page_links_to_set_password(signed_in):
    owner = _user("owner", "sana@example.com", "Sana Ahmed")

    page = signed_in.get(reverse("admin:accounts_user_change", args=[owner.pk]))

    assert _set_url(owner) in page.content.decode()


def test_the_admin_sets_the_password_they_chose(signed_in):
    owner = _user("owner", "sana@example.com", "Sana Ahmed")
    chosen = "Green-Lantern-River-77"

    signed_in.post(_set_url(owner), {"password": chosen, "password_again": chosen})

    owner.refresh_from_db()
    assert owner.check_password(chosen)
    assert not mail.outbox


def test_the_chosen_password_can_be_emailed(signed_in):
    owner = _user("owner", "sana@example.com", "Sana Ahmed")
    chosen = "Green-Lantern-River-77"

    signed_in.post(
        _set_url(owner), {"password": chosen, "password_again": chosen, "email_owner": "on"}
    )

    assert chosen in mail.outbox[0].body


def test_mismatched_or_weak_passwords_change_nothing(signed_in):
    owner = _user("owner", "sana@example.com", "Sana Ahmed")

    signed_in.post(_set_url(owner), {"password": "Green-Lantern-River-77", "password_again": "x"})
    signed_in.post(_set_url(owner), {"password": "123", "password_again": "123"})

    owner.refresh_from_db()
    assert owner.check_password("old-Password-1")


def test_a_cashier_password_cannot_be_set(signed_in):
    cashier = _user("cashier", None, "Bilal Raza")

    signed_in.post(
        _set_url(cashier),
        {"password": "Green-Lantern-River-77", "password_again": "Green-Lantern-River-77"},
    )

    cashier.refresh_from_db()
    assert cashier.check_password("old-Password-1")
