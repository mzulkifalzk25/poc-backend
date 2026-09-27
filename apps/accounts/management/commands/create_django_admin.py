from getpass import getpass

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.use_cases.django_admin import save_django_admin


class Command(BaseCommand):
    help = "Create the one Django admin account for DJANGO_ADMIN_EMAIL, or reset its password."

    def handle(self, *args, **options) -> None:
        email = settings.DJANGO_ADMIN_EMAIL.strip().lower()
        if not email:
            raise CommandError("Set DJANGO_ADMIN_EMAIL in the server's .env first.")
        created = save_django_admin(email, self._ask_password())
        action = "Created" if created else "Updated"
        self.stdout.write(f"{action} the Django admin {email}.")

    def _ask_password(self) -> str:
        password = getpass("Password: ")
        if password != getpass("Password (again): "):
            raise CommandError("The passwords do not match.")
        try:
            validate_password(password)
        except ValidationError as error:
            raise CommandError(" ".join(error.messages)) from None
        return password
