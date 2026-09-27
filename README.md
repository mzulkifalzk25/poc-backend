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

## Django admin

```
python manage.py create_platform_admin --email you@example.com   # asks for the password twice
```

Signs in at `/admin/` with that email and password. Only a platform admin can
open the admin; store owners and cashiers are refused even with a correct
password, and a platform admin cannot sign in to the store app. Running the
command again for the same email resets the password. Store data is view-only
in the admin (the app's own rules and activity log apply to every change);
tenants and platform admin accounts can be edited.

## Layout

Clean architecture per app under `apps/`: `domain/` (plain Python rules),
`use_cases/` (one action per function or class), `repositories/` (a small
interface plus its Django ORM implementation), `api/` (thin DRF views,
serializers, urls, no business logic), `models.py`, `tests/`. Settings are
split into `config/settings/{base,dev,prod}.py`.
