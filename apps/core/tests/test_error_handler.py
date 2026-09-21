from rest_framework.exceptions import NotAuthenticated, ValidationError
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory
from rest_framework.views import APIView

from apps.core.api.exceptions import ApiError


class _RaisingView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        raise_kind = request.query_params.get("raise")
        if raise_kind == "api_error":
            raise ApiError(
                code="code_exists",
                message="Counter code already exists.",
                status_code=409,
                fields={"code": ["already in use"]},
            )
        if raise_kind == "validation":
            raise ValidationError({"full_name": ["This field is required."]})
        if raise_kind == "not_authenticated":
            raise NotAuthenticated()
        return Response({"ok": True})


factory = APIRequestFactory()


def _call(raise_kind: str):
    request = factory.get(f"/x/?raise={raise_kind}")
    return _RaisingView.as_view()(request)


def test_api_error_uses_its_own_code_message_and_fields():
    response = _call("api_error")

    assert response.status_code == 409
    assert response.data == {
        "error": {
            "code": "code_exists",
            "message": "Counter code already exists.",
            "fields": {"code": ["already in use"]},
        }
    }


def test_validation_error_reports_field_errors():
    response = _call("validation")

    assert response.status_code == 400
    assert response.data["error"]["code"] == "validation_error"
    assert response.data["error"]["fields"] == {"full_name": ["This field is required."]}


def test_not_authenticated_uses_drf_default_code():
    # No authentication class is configured on the view, so DRF reports 403
    # rather than 401 (it only challenges with 401 when an authenticator is
    # present); real endpoints wire up JWT auth and get a real 401.
    response = _call("not_authenticated")

    assert response.status_code == 403
    assert response.data["error"]["code"] == "not_authenticated"
    assert response.data["error"]["fields"] == {}
