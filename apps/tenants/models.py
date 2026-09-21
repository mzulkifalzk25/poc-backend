from django.db import models


class Tenant(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)
    plan = models.CharField(max_length=50, default="poc")
    status = models.CharField(max_length=20, default="active")
    timezone = models.CharField(max_length=50, default="Asia/Karachi")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return self.name
