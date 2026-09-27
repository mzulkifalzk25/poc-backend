from getpass import getpass

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.utils.text import slugify

from apps.accounts.use_cases.onboard_tenant import NewTenant, TenantSlugTakenError, onboard_tenant


class Command(BaseCommand):
    help = "Create a new mart (tenant) with its first owner account."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--store-name", required=True, help="The mart's name, e.g. 'Fresh Basket Mart'"
        )
        parser.add_argument("--owner-name", required=True, help="The owner's full name")
        parser.add_argument("--email", help="The owner's sign-in email")
        parser.add_argument("--username", help="The owner's sign-in username, if no email")
        parser.add_argument("--slug", help="Tenant slug; derived from --store-name if left out")

    def handle(self, *args, **options) -> None:
        email = (options.get("email") or "").strip() or None
        username = (options.get("username") or "").strip() or None
        if not email and not username:
            raise CommandError("Pass --email or --username for the owner to sign in with.")
        slug = options.get("slug") or slugify(options["store_name"])
        password = self._ask_password()
        try:
            tenant, owner = onboard_tenant(
                NewTenant(
                    tenant_name=options["store_name"],
                    tenant_slug=slug,
                    owner_name=options["owner_name"],
                    owner_email=email,
                    owner_username=username,
                    password=password,
                )
            )
        except TenantSlugTakenError:
            raise CommandError(f"A tenant with the slug '{slug}' already exists.") from None
        self.stdout.write(f"Created {tenant.name} (tenant {tenant.id}), owner {owner.full_name}.")
        self.stdout.write(f"Sign in with {email or username} and the password you just typed.")

    def _ask_password(self) -> str:
        password = getpass("Owner password: ")
        if password != getpass("Owner password (again): "):
            raise CommandError("The passwords do not match.")
        try:
            validate_password(password)
        except ValidationError as error:
            raise CommandError(" ".join(error.messages)) from None
        return password
