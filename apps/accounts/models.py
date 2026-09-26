from django.contrib.auth.base_user import AbstractBaseUser
from django.db import models
from django.db.models.functions import Lower

from apps.accounts.domain.role_rules import ROLES
from apps.core.models import TenantModel

_ROLE_CHOICES = [(role, role.capitalize()) for role in ROLES]


class User(TenantModel, AbstractBaseUser):
    """Owner and manager sign in with `password` (from AbstractBaseUser);
    cashiers sign in with `pin_hash` and have no email, username or password.

    USERNAME_FIELD is set to `id` as a formality: AbstractBaseUser requires
    one, but there is no single natural login field across roles (owner and
    manager log in by email or username, cashiers by PIN against a typed
    name), so login is handled entirely by our own use cases, not Django's
    `authenticate()`.
    """

    full_name = models.CharField(max_length=255)
    role = models.CharField(max_length=10, choices=_ROLE_CHOICES)
    email = models.EmailField(null=True, blank=True)
    username = models.CharField(max_length=150, null=True, blank=True)
    pin_hash = models.CharField(max_length=255, null=True, blank=True)
    pin_verifier = models.CharField(max_length=255, null=True, blank=True)
    default_counter_id = models.BigIntegerField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    last_active_at = models.DateTimeField(null=True, blank=True)

    USERNAME_FIELD = "id"
    REQUIRED_FIELDS: list[str] = []

    class Meta:
        constraints = [
            models.UniqueConstraint(
                "tenant_id",
                Lower("email"),
                name="uniq_user_tenant_email_lower",
                condition=models.Q(email__isnull=False),
            ),
            models.UniqueConstraint(
                "tenant_id",
                Lower("username"),
                name="uniq_user_tenant_username_lower",
                condition=models.Q(username__isnull=False),
            ),
            models.UniqueConstraint(
                "tenant_id",
                Lower("full_name"),
                name="uniq_user_tenant_cashier_name_lower",
                condition=models.Q(role="cashier"),
            ),
        ]

    def __str__(self) -> str:
        return self.full_name


class PinDelay(TenantModel):
    """Cashier PIN delay state per cashier and counter (contract section 4.1)."""

    counter_id = models.BigIntegerField()
    user_id = models.BigIntegerField()
    fail_count = models.PositiveIntegerField(default=0)
    next_allowed_at = models.DateTimeField(null=True, blank=True)
    last_failed_at = models.DateTimeField(null=True, blank=True)
    unlocked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant_id", "counter_id", "user_id"], name="uniq_pin_delay_counter_user"
            ),
        ]

    def __str__(self) -> str:
        return f"PIN delay for user {self.user_id} at counter {self.counter_id}"
