from dataclasses import dataclass

from django.conf import settings
from django.core.mail import send_mail

from apps.accounts.use_cases.onboard_tenant import OnboardedTenant


@dataclass(frozen=True)
class WelcomeEmail:
    to: str
    subject: str
    body: str


def build_welcome_email(onboarded: OnboardedTenant, login_url: str) -> WelcomeEmail:
    owner, tenant = onboarded.owner, onboarded.tenant
    body = (
        f"Hello {owner.full_name},\n\n"
        f"Your mart {tenant.name} is ready on MartDesk.\n\n"
        f"Sign in here: {login_url}\n"
        f"Email: {owner.email}\n"
        f"Password: {onboarded.password}\n\n"
        "After signing in you can add your products and your cashiers.\n"
    )
    return WelcomeEmail(owner.email, f"Your MartDesk account for {tenant.name}", body)


def send_owner_welcome(onboarded: OnboardedTenant, login_url: str | None = None) -> None:
    email = build_welcome_email(onboarded, login_url or settings.STORE_APP_URL)
    send_mail(email.subject, email.body, None, [email.to], fail_silently=False)
