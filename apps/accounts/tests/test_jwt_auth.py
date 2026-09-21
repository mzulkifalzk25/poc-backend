import pytest
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import User


class _WhoAmI(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({"user_id": request.user.id})


factory = APIRequestFactory()


@pytest.mark.django_db
def test_a_valid_access_token_authenticates_the_request():
    user = User.objects.create(tenant_id=1, full_name="Sana Ahmed", role="owner", username="sana")
    access = str(RefreshToken.for_user(user).access_token)

    request = factory.get("/x/", HTTP_AUTHORIZATION=f"Bearer {access}")
    response = _WhoAmI.as_view()(request)

    assert response.status_code == 200
    assert response.data == {"user_id": user.id}


@pytest.mark.django_db
def test_a_missing_token_is_rejected():
    request = factory.get("/x/")
    response = _WhoAmI.as_view()(request)

    assert response.status_code in (401, 403)


@pytest.mark.django_db
def test_a_malformed_token_is_rejected():
    request = factory.get("/x/", HTTP_AUTHORIZATION="Bearer not-a-real-token")
    response = _WhoAmI.as_view()(request)

    assert response.status_code == 401
