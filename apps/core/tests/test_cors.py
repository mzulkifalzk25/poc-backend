from django.test import Client


def test_the_frontend_origin_may_call_the_api():
    response = Client().options(
        "/api/v1/auth/login",
        HTTP_ORIGIN="http://localhost:5173",
        HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
        HTTP_ACCESS_CONTROL_REQUEST_HEADERS="content-type",
    )

    assert response["Access-Control-Allow-Origin"] == "http://localhost:5173"


def test_another_origin_is_not_allowed():
    response = Client().options(
        "/api/v1/auth/login",
        HTTP_ORIGIN="https://evil.example",
        HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
    )

    assert "Access-Control-Allow-Origin" not in response
