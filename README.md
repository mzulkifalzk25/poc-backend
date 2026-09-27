# poc-backend

MartDesk backend: Django, Django REST Framework, PostgreSQL. Proof of concept for a single mart.

## Setup

```
python -m venv .venv && source .venv/bin/activate
pip install -r requirements/dev.txt
docker compose -f deploy/docker-compose.dev.yml up -d db     # PostgreSQL for development
python manage.py migrate
python manage.py runserver
```

Copy `.env.example` to `.env` and fill in values, or rely on the defaults in
`config/settings/base.py`, which match `deploy/docker-compose.dev.yml`
(database on host port 5434, to avoid clashing with other Postgres instances
on this machine).

## Test and lint

```
pytest                                        # all tests
ruff check . && ruff format --check .         # lint and format
python manage.py makemigrations --check --dry-run
```

## Seed data

```
python scripts/seed_sample_data.py            # small POC data set
python scripts/seed_sample_data.py --large    # 18,462 products, 40 counters (load test)
```

Creates the demo store "Fresh Basket Mart" (owner `sana`, cashiers Zainab
Khan, Bilal Raza, Hina Malik and deactivated Usman Tariq, counters 001 and
002 activated, 003 not activated, 7 categories, 10 products). It prints the
owner password, the cashier PINs, the device tokens of counters 001 and 002
(`Authorization: Device <token>`) and an activation code for counter 003
(single use, 15 minutes). Safe to run twice: each run resets only the demo
tenant and prints new values. Activity-log entries from earlier runs stay
(the log is append-only).

`--large` builds the long-term target on the same shape: the small set plus
generated products up to 18,462 in total (same 7 categories, valid `896…`
barcodes, costs 80 to 90 percent of price, some low and out of stock), and
counters 004 to 040, each activated with its own device token. The generated
catalogue is the same on every run.

## Report rollup

Reports never read raw bills. The rollup adds uploaded bills to the pre-summed
tables (`sales_hourly`, `sales_daily`, `sales_daily_product`,
`sales_daily_cashier`), bucketed by the time of sale in the store's time zone.

```
python manage.py run_rollup                   # one pass: everything waiting now
python manage.py run_rollup --loop            # a pass every 30 s (--interval to change)
```

Safe to run twice: each bill is counted once. Only one runner works at a time
(a second one exits with "Another rollup is running."). In production run the
loop under systemd, for example:

```
[Service]
ExecStart=/srv/poc-backend/.venv/bin/python manage.py run_rollup --loop
WorkingDirectory=/srv/poc-backend
Restart=always
```

SIGTERM (systemctl stop) finishes the current pass, then stops.

## Django admin

The Django admin at `/admin/` is for the product maintainer only: exactly one
account, whose email is `DJANGO_ADMIN_EMAIL` in `.env`. Store owners and
cashiers use the store app; they can never sign in to the Django admin, even
with a correct password, and the Django admin cannot sign in to the store app.
With `DJANGO_ADMIN_EMAIL` empty, nobody can sign in.

```
python manage.py create_django_admin    # asks for the password twice
```

Creates that one account, or resets its password when run again. Store data
is view-only in the admin (the app's own rules and activity log apply to every
change); tenants and the admin's own name and active flag can be edited.

## Layout

Clean architecture per app under `apps/`: `domain/` (plain Python rules),
`use_cases/` (one action per function or class), `repositories/` (a small
interface plus its Django ORM implementation), `api/` (thin DRF views,
serializers, urls, no business logic), `models.py`, `tests/`. Settings are
split into `config/settings/{base,dev,prod}.py`.
