# backend

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

Reports never read raw bills. The rollup adds uploaded bills and returns to the
pre-summed tables (`sales_hourly`, `sales_daily`, `sales_daily_product`,
`sales_daily_cashier`), bucketed by the time of sale or return in the store's
time zone. Sales stay gross; returns fill the refund columns.

```
python manage.py run_rollup                   # one pass: everything waiting now
python manage.py run_rollup --loop            # a pass every 30 s (--interval to change)
```

Safe to run twice: each bill is counted once. Only one runner works at a time
(a second one exits with "Another rollup is running."). In production run the
loop under systemd, for example:

```
[Service]
ExecStart=/srv/backend/.venv/bin/python manage.py run_rollup --loop
WorkingDirectory=/srv/backend
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

## Adding a mart and its owner

In the Django admin open **Tenants → Add** (or `/admin/tenants/tenant/onboard/`).
Fill in the mart, the owner's name and email, and optionally a password (empty
means one is generated). The mart, its settings and the owner account are
created, and the owner gets an email with the login link, their email and the
password. If the email cannot be sent, the mart is still created and the admin
page shows the password once so you can pass it on yourself.

Set these in `.env` (see `.env.example`): `STORE_APP_URL` (the frontend address
sent as the login link) and the SMTP values `EMAIL_HOST`, `EMAIL_PORT`,
`EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS` / `EMAIL_USE_SSL`,
`DEFAULT_FROM_EMAIL`. The command line still works:
`python manage.py create_store_owner --store-name ... --owner-first-name ... --owner-last-name ... --email ...`.

To choose an owner's or manager's password yourself: open the user in **Users**
and click **Set password** (top right); optionally tick the box to email it. Only
the hash is stored.

To reset to a random password instead: **Users**, tick them, choose
**Reset password and email it to the selected owners and managers**, then Go.
A new random password is emailed with the login link (shown on the page once
if the email fails).

## Layout

Clean architecture per app under `apps/`: `domain/` (plain Python rules),
`use_cases/` (one action per function or class), `repositories/` (a small
interface plus its Django ORM implementation), `api/` (thin DRF views,
serializers, urls, no business logic), `models.py`, `tests/`. Settings are
split into `config/settings/{base,dev,prod}.py`.
