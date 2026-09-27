from getpass import getpass

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email

from apps.accounts.use_cases.platform_admin import save_platform_admin


class Command(BaseCommand):
    help = "Create the platform admin that signs in to the Django admin, or reset its password."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--email", required=True)

    def handle(self, *args, email: str, **options) -> None:
        try:
            validate_email(email.strip())
        except ValidationError:
            raise CommandError("Enter a valid email address.") from None
        created = save_platform_admin(email, self._ask_password())
        action = "Created" if created else "Updated"
        self.stdout.write(f"{action} the platform admin {email.strip().lower()}.")

    def _ask_password(self) -> str:
        password = getpass("Password: ")
        if password != getpass("Password (again): "):
            raise CommandError("The passwords do not match.")
        try:
            validate_password(password)
        except ValidationError as error:
            raise CommandError(" ".join(error.messages)) from None
        return password
