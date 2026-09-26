import pytest
from rest_framework.test import APIClient


def test_a_bad_access_token_is_401_token_not_valid_without_fields():
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION="Bearer not-a-token")

    response = client.get("/api/v1/me")

    assert response.status_code == 401
    error = response.json()["error"]
    assert error["code"] == "token_not_valid"
    assert error["fields"] == {}


@pytest.mark.django_db
def test_a_bad_refresh_token_is_401_token_not_valid_without_fields():
    response = APIClient().post("/api/v1/auth/refresh", {"refresh": "not-a-token"}, format="json")

    assert response.status_code == 401
    error = response.json()["error"]
    assert error["code"] == "token_not_valid"
    assert error["fields"] == {}


@pytest.mark.django_db
def test_missing_refresh_is_still_a_field_error():
    response = APIClient().post("/api/v1/auth/refresh", {}, format="json")

    assert response.status_code == 400
    assert response.json()["error"]["fields"]["refresh"]
