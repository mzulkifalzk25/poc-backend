from django.contrib import admin


class ReadOnlyAdmin(admin.ModelAdmin):
    """Store data is written only through the app's use cases, which apply the
    business rules and write the activity log, so the admin only shows it."""

    def has_add_permission(self, request, obj=None) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False
