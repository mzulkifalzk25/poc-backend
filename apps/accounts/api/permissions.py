from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView

from apps.accounts.domain.role_rules import CASHIER, OWNER


class IsOwner(BasePermission):
    message = "Owner access required."

    def has_permission(self, request: Request, view: APIView) -> bool:
        user = request.user
        return bool(user and user.is_authenticated and getattr(user, "role", None) == OWNER)


class IsOwnerOrCashier(BasePermission):
    """Roles O, C: the manager role has no POC screens."""

    message = "Owner or cashier access required."

    def has_permission(self, request: Request, view: APIView) -> bool:
        user = request.user
        role = getattr(user, "role", None)
        return bool(user and user.is_authenticated and role in (OWNER, CASHIER))
