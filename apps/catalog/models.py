from django.db import models
from django.db.models.functions import Lower

from apps.core.models import TenantModel


class Category(TenantModel):
    name = models.CharField(max_length=100)
    tint = models.CharField(max_length=20)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                "tenant_id", Lower("name"), name="uniq_category_tenant_name_lower"
            ),
        ]

    def __str__(self) -> str:
        return self.name
