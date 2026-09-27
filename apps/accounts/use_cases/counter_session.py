from apps.accounts.repositories.users import UserRepository, user_repository
from apps.tenants.use_cases.device_access import DeviceRevokedError, ensure_device_live


def ensure_session_device_live(
    user_id: str | None, device_id: int, users: UserRepository = user_repository
) -> None:
    """A counter session's refresh token is refused once its PC is revoked,
    or when its user no longer exists."""
    tenant_id = users.tenant_id_of(user_id)
    if tenant_id is None:
        raise DeviceRevokedError
    ensure_device_live(tenant_id, device_id)
