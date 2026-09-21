import pytest
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.api.permissions import IsOwner
from apps.accounts.models import User


class _OwnerOnlyView(APIView):
    permission_classes = [IsOwner]

    def get(self, request):
        return Response({"ok": True})


factory = APIRequestFactory()


def _token_for(user: User) -> str:
    return str(RefreshToken.for_user(user).access_token)


@pytest.mark.django_db
def test_owner_is_allowed():
    owner = User.objects.create(tenant_id=1, full_name="Sana Ahmed", role="owner", username="sana")

    request = factory.get("/x/", HTTP_AUTHORIZATION=f"Bearer {_token_for(owner)}")
    response = _OwnerOnlyView.as_view()(request)

    assert response.status_code == 200


@pytest.mark.django_db
def test_cashier_is_forbidden():
    cashier = User.objects.create(
        tenant_id=1, full_name="Zainab Khan", role="cashier", pin_hash="x"
    )

    request = factory.get("/x/", HTTP_AUTHORIZATION=f"Bearer {_token_for(cashier)}")
    response = _OwnerOnlyView.as_view()(request)

    assert response.status_code == 403


@pytest.mark.django_db
def test_manager_is_forbidden():
    manager = User.objects.create(
        tenant_id=1, full_name="Manager Person", role="manager", username="manager1"
    )

    request = factory.get("/x/", HTTP_AUTHORIZATION=f"Bearer {_token_for(manager)}")
    response = _OwnerOnlyView.as_view()(request)

    assert response.status_code == 403


def test_unauthenticated_is_rejected():
    request = factory.get("/x/")
    response = _OwnerOnlyView.as_view()(request)

    assert response.status_code in (401, 403)
