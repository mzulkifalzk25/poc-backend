import pytest
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.api.authentication import DeviceBoundJWTAuthentication
from apps.accounts.models import User
from apps.tenants.api.device_auth import DeviceAuthentication
from apps.tenants.api.permissions import IsCounterDevice
from apps.tenants.domain.device_token import generate_device_token, hash_device_token
from apps.tenants.models import Counter, Device

from .helpers import make_tenant

factory = APIRequestFactory()


class _DeviceOnly(APIView):
    authentication_classes = [DeviceBoundJWTAuthentication, DeviceAuthentication]
    permission_classes = [IsCounterDevice]

    def get(self, request):
        user = request.user
        return Response({"tenant_id": user.tenant_id, "counter_id": user.counter_id})


class _SignedIn(APIView):
    def get(self, request):
        return Response({"user_id": request.user.id})


def _call(view, authorization: str | None):
    headers = {"HTTP_AUTHORIZATION": authorization} if authorization else {}
    return view.as_view()(factory.get("/x/", **headers))


@pytest.fixture
def tenant():
    return make_tenant()


@pytest.fixture
def counter(tenant) -> Counter:
    return Counter.objects.create(tenant_id=tenant.id, name="Counter 2", code="002")


def _device(counter: Counter, revoked: bool = False) -> tuple[Device, str]:
    token = generate_device_token()
    device = Device.objects.create(
        tenant_id=counter.tenant_id,
        counter=counter,
        token_hash=hash_device_token(token),
        revoked_at=timezone.now() if revoked else None,
    )
    return device, token


def _cashier_access(tenant_id: int, device_id: int | None) -> str:
    cashier = User.objects.create(tenant_id=tenant_id, full_name="Zainab Khan", role="cashier")
    access = RefreshToken.for_user(cashier).access_token
    if device_id is not None:
        access["device_id"] = device_id
    return f"Bearer {access}"


@pytest.mark.django_db
def test_a_live_device_token_identifies_the_tenant_and_counter(tenant, counter):
    _, token = _device(counter)

    response = _call(_DeviceOnly, f"Device {token}")

    assert response.status_code == 200
    assert response.data == {"tenant_id": tenant.id, "counter_id": counter.id}


@pytest.mark.django_db
def test_devices_of_two_tenants_resolve_to_their_own_tenant(counter):
    other_counter = Counter.objects.create(
        tenant_id=make_tenant("other-mart").id, name="Counter 2", code="002"
    )
    _, token = _device(counter)
    _, other_token = _device(other_counter)

    mine = _call(_DeviceOnly, f"Device {token}").data
    theirs = _call(_DeviceOnly, f"Device {other_token}").data

    assert mine["tenant_id"] == counter.tenant_id
    assert theirs["tenant_id"] == other_counter.tenant_id
    assert mine["counter_id"] != theirs["counter_id"]


@pytest.mark.django_db
def test_a_revoked_device_gets_401_device_revoked(counter):
    _, token = _device(counter, revoked=True)

    response = _call(_DeviceOnly, f"Device {token}")

    assert response.status_code == 401
    assert response.data["error"]["code"] == "device_revoked"


@pytest.mark.django_db
@pytest.mark.parametrize("header", ["Device not-a-token", "Device", "Device a b"])
def test_an_unknown_or_malformed_device_token_is_401(header):
    response = _call(_DeviceOnly, header)

    assert response.status_code == 401
    assert response.data["error"]["code"] == "device_invalid"


def test_no_credentials_is_401_on_a_device_endpoint():
    response = _call(_DeviceOnly, None)

    assert response.status_code == 401


@pytest.mark.django_db
def test_a_signed_in_user_is_not_a_device(tenant):
    owner = User.objects.create(tenant_id=tenant.id, full_name="Sana", role="owner", username="s")

    response = _call(_DeviceOnly, f"Bearer {RefreshToken.for_user(owner).access_token}")

    assert response.status_code == 403


@pytest.mark.django_db
def test_a_device_token_is_not_a_signed_in_user(counter):
    _, token = _device(counter)

    response = _call(_SignedIn, f"Device {token}")

    assert response.status_code == 401


@pytest.mark.django_db
def test_a_cashier_token_bound_to_a_live_pc_works(tenant, counter):
    device, _ = _device(counter)

    response = _call(_SignedIn, _cashier_access(tenant.id, device.id))

    assert response.status_code == 200


@pytest.mark.django_db
def test_a_cashier_token_bound_to_a_revoked_pc_gets_device_revoked(tenant, counter):
    device, _ = _device(counter, revoked=True)

    response = _call(_SignedIn, _cashier_access(tenant.id, device.id))

    assert response.status_code == 401
    assert response.data["error"]["code"] == "device_revoked"


@pytest.mark.django_db
def test_a_cashier_token_bound_to_another_tenants_pc_is_refused(counter):
    device, _ = _device(counter)
    other_tenant = make_tenant("other-mart")

    response = _call(_SignedIn, _cashier_access(other_tenant.id, device.id))

    assert response.status_code == 401
    assert response.data["error"]["code"] == "device_revoked"


@pytest.mark.django_db
def test_a_token_without_a_device_claim_is_unaffected(tenant):
    response = _call(_SignedIn, _cashier_access(tenant.id, None))

    assert response.status_code == 200
