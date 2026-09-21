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
python scripts/seed_sample_data.py            # small POC data set (add --large for 18,462 products, --history for sample bills)
```

`scripts/seed_sample_data.py` is added in a later step; the flags land with
the steps that need them.

## Layout

Clean architecture per app under `apps/`: `domain/` (plain Python rules),
`use_cases/` (one action per function or class), `repositories/` (a small
interface plus its Django ORM implementation), `api/` (thin DRF views,
serializers, urls, no business logic), `models.py`, `tests/`. Settings are
split into `config/settings/{base,dev,prod}.py`.
