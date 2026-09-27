"""Seeds the demo tenant "Fresh Basket Mart" for development.

Safe to run twice: each run resets only the demo tenant and prints fresh
sign-in details (owner password, cashier PINs, counter device tokens and an
activation code for the counter that is not activated yet).

    python scripts/seed_sample_data.py            # small POC data set
    python scripts/seed_sample_data.py --large    # 18,462 products, 40 counters
"""

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    args = _parse_args()
    sys.path.insert(0, str(ROOT))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
    import django

    django.setup()
    from django.utils import timezone

    from scripts.seed.demo_tenant import seed_demo_tenant
    from scripts.seed.large_catalogue import large_counters, large_products
    from scripts.seed.sample_data import COUNTERS, PRODUCTS
    from scripts.seed.summary import summary_lines

    if args.large:
        result = seed_demo_tenant(timezone.now(), large_counters(), large_products())
    else:
        result = seed_demo_tenant(timezone.now(), COUNTERS, PRODUCTS)
    print("\n".join(summary_lines(result)))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reset and seed the demo tenant.")
    parser.add_argument(
        "--large",
        action="store_true",
        help="18,462 products and 40 counters (the long-term target, for load tests)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    main()
