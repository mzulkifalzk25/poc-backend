import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.tenants.models import Tenant

REFRESH_URL = "/api/v1/auth/refresh"
LOGOUT_URL = "/api/v1/auth/logout"
ME_URL = "/api/v1/me"


@pytest.fixture
def client() -> APIClient:
    return APIClient()


@pytest.fixture
def owner_tokens(client):
    tenant = Tenant.objects.create(name="Fresh Basket Mart", slug="fresh-basket-mart")
    user = User(tenant_id=tenant.id, full_name="Sana Ahmed", role="owner", username="sana")
    user.set_password("correct horse battery staple")
    user.save()

    response = client.post(
        "/api/v1/auth/login", {"login": "sana", "password": "correct horse battery staple"}
    )
    return response.json(), tenant, user


@pytest.mark.django_db
def test_refresh_issues_a_new_token_pair(client, owner_tokens):
    tokens, _tenant, _user = owner_tokens

    response = client.post(REFRESH_URL, {"refresh": tokens["refresh"]})

    assert response.status_code == 200
    body = response.json()
    assert body["access"] and body["refresh"]
    assert body["refresh"] != tokens["refresh"]


@pytest.mark.django_db
def test_a_rotated_refresh_token_cannot_be_reused(client, owner_tokens):
    tokens, _tenant, _user = owner_tokens

    client.post(REFRESH_URL, {"refresh": tokens["refresh"]})
    second_attempt = client.post(REFRESH_URL, {"refresh": tokens["refresh"]})

    assert second_attempt.status_code == 401


@pytest.mark.django_db
def test_logout_blacklists_the_refresh_token(client, owner_tokens):
    tokens, _tenant, _user = owner_tokens
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")

    response = client.post(LOGOUT_URL, {"refresh": tokens["refresh"]})

    assert response.status_code == 204
    refresh_after_logout = client.post(REFRESH_URL, {"refresh": tokens["refresh"]})
    assert refresh_after_logout.status_code == 401


@pytest.mark.django_db
def test_logout_requires_authentication(client, owner_tokens):
    tokens, _tenant, _user = owner_tokens

    response = client.post(LOGOUT_URL, {"refresh": tokens["refresh"]})

    assert response.status_code == 401


@pytest.mark.django_db
def test_me_returns_the_signed_in_user_and_tenant(client, owner_tokens):
    tokens, tenant, user = owner_tokens
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")

    response = client.get(ME_URL)

    assert response.status_code == 200
    body = response.json()
    assert body["user"]["id"] == user.id
    assert body["tenant"]["slug"] == tenant.slug
    assert body["permissions"] == {}


@pytest.mark.django_db
def test_me_requires_authentication(client):
    response = client.get(ME_URL)

    assert response.status_code == 401
