from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.reports.use_cases.rollup import DEFAULT_BATCH_SIZE, roll_up_pending


class Command(BaseCommand):
    help = "Add every uploaded bill not rolled up yet to the report tables."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)

    def handle(self, *args, batch_size: int, **options) -> None:
        added = roll_up_pending(timezone.now(), batch_size)
        self.stdout.write(f"Rolled up {added} bills.")
