import signal
import time

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.reports.use_cases.rollup import DEFAULT_BATCH_SIZE, RollupAlreadyRunning, run_rollup


class Command(BaseCommand):
    help = (
        "Add every uploaded bill and return not rolled up yet to the report tables. "
        "With --loop, keep doing it every --interval seconds (for systemd)."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument("--loop", action="store_true")
        parser.add_argument("--interval", type=float, default=30)
        parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)

    def handle(self, *args, loop: bool, interval: float, batch_size: int, **options) -> None:
        stopping = False

        def stop(signum, frame) -> None:
            nonlocal stopping
            stopping = True

        if loop:
            signal.signal(signal.SIGTERM, stop)
        try:
            run_rollup(
                timezone.now,
                loop=loop,
                interval=interval,
                batch_size=batch_size,
                keep_going=lambda: not stopping,
                sleep=time.sleep,
                on_pass=lambda added: self._report(added, quiet_when_idle=loop),
            )
        except RollupAlreadyRunning:
            raise CommandError("Another rollup is running.") from None

    def _report(self, added: int, quiet_when_idle: bool) -> None:
        if added or not quiet_when_idle:
            self.stdout.write(f"Rolled up {added} bills and returns.")
