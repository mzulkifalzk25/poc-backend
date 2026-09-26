from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView

from .device_auth import CounterDevice


class IsCounterDevice(BasePermission):
    message = "An activated counter PC is required."

    def has_permission(self, request: Request, view: APIView) -> bool:
        return isinstance(request.user, CounterDevice)
