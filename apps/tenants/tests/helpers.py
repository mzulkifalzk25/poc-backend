from uuid import uuid4

from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import User
from apps.tenants.models import Tenant


def make_tenant(slug: str = "fresh-basket-mart") -> Tenant:
    return Tenant.objects.create(name=slug.replace("-", " ").title(), slug=slug)


def authed_client(tenant: Tenant, role: str = "owner") -> tuple[APIClient, User]:
    if role == "cashier":
        name = f"Cashier {uuid4().hex[:8]}"
        user = User(tenant_id=tenant.id, full_name=name, role=role, pin_hash="x")
    else:
        username = f"owner-{uuid4().hex[:8]}"
        user = User(tenant_id=tenant.id, full_name="Owner", role=role, username=username)
        user.set_password("password123")
    user.save()
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    return client, user
