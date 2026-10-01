from django.conf import settings
from django.contrib.auth.base_user import AbstractBaseUser
from django.db import models
from django.db.models.functions import Lower

from apps.accounts.domain.django_admin import is_django_admin_email
from apps.accounts.domain.role_rules import ROLES
from apps.core.models import TenantModel

_ROLE_CHOICES = [(role, role.capitalize()) for role in ROLES]


class User(TenantModel, AbstractBaseUser):
    """Every role signs in with email or username and `password` (from
    AbstractBaseUser), over the network; there is no offline sign-in.

    USERNAME_FIELD is set to `id` as a formality: AbstractBaseUser requires
    one, but there is no single natural login field across roles (staff log
    in by email or username), so login is handled entirely by our own use
    cases, not Django's `authenticate()`.
    """

    full_name = models.CharField(max_length=255)
    role = models.CharField(max_length=10, choices=_ROLE_CHOICES)
    email = models.EmailField(null=True, blank=True)
    username = models.CharField(max_length=150, null=True, blank=True)
    phone = models.CharField(max_length=32, blank=True, default="")
    default_counter_id = models.BigIntegerField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    last_active_at = models.DateTimeField(null=True, blank=True)
    is_django_admin = models.BooleanField(default=False)

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

    @property
    def is_staff(self) -> bool:
        """Only the one active Django admin, with the email set on the server,
        may open the Django admin."""
        return (
            self.is_active
            and self.is_django_admin
            and is_django_admin_email(self.email, settings.DJANGO_ADMIN_EMAIL)
        )

    @property
    def is_superuser(self) -> bool:
        return self.is_staff

    def has_perm(self, perm: str, obj: object = None) -> bool:
        return self.is_staff

    def has_module_perms(self, app_label: str) -> bool:
        return self.is_staff
