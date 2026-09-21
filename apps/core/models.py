from django.db import models


class TenantQuerySet(models.QuerySet):
    def for_tenant(self, tenant_id: int) -> TenantQuerySet:
        return self.filter(tenant_id=tenant_id)


class TenantManager(models.Manager.from_queryset(TenantQuerySet)):
    pass


class TenantModel(models.Model):
    """Abstract base for every tenant-owned table.

    `tenant_id` is a plain column, not a Django ForeignKey: the tenant always
    comes from the signed-in request's token, never a relation traversal, and
    a plain column avoids ordering every app's migrations behind `tenants`.
    """

    tenant_id = models.BigIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantManager()

    class Meta:
        abstract = True
