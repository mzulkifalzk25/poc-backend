# MartDesk: API_CONTRACT.md (POC, v4)

Status: **v4, in active development** (backend and frontend are being built against it). Agreed 20 Sep 2026; last changed 26 Sep 2026 (section 8, items 21 to 23).
Sources: the project handoff notes (kept outside the repositories) and the design canvas (28 boards: 23 POC screens, 4 Phase 2 boards, 1 shared sidebar). The exported screens are kept outside the repositories.
v4 = v3.1 with the simplified returns (no PIN, no approvals), the Money trail report, the new sign-in, counter management and cashier PIN delays. The change list is in section 8.

## 0. Scope

**In the POC:** auth (owner password, cashier PIN), tenants, counters, activation codes and devices, staff, categories, products (archive), stock (adjust, receive), cashier billing with offline sync, held bills, shifts, sales list, reports, **Money trail**, settings, **simple returns and refunds (no PIN)**, **activity log (recording and admin screen)**, audit-event upload.
**Phase 2 (schema kept ready where noted, no endpoints):** discounts with manager PIN, owner-PIN approval for returns, refund from Admin Sales, live counters, bulk price update, split payment, loyalty, branches.

## 1. Repositories and folders

Two repositories, cloned side by side in `~/Desktop/poc/`. Both follow clean architecture: domain, then use cases, then adapters, then frameworks. Domain code never imports Django, DRF, React, Dexie or the network.

```
poc-backend/                     Django, Django REST Framework, PostgreSQL
├─ README.md, manage.py, pyproject.toml (ruff, pytest), requirements/{base,dev}.txt, .env.example
├─ docs/         API_CONTRACT.md · runbooks/{backup-restore,outage-recovery}.md
├─ config/       settings/{base,dev,prod}.py, urls.py, wsgi.py
├─ apps/         every app has: domain/ · use_cases/ · repositories/ · api/ · models.py · tests/
│  ├─ core/        Money, errors, TenantModel, TenantManager, permissions, pagination, error handler
│  ├─ tenants/     Tenant, TenantSettings, Counter, DeviceCode, Device
│  ├─ accounts/    User, PinDelay, JWT, owner login, PIN login, unlock
│  ├─ catalog/     Category, Product, PriceHistory, sync
│  ├─ inventory/   StockLevel, StockMovement, Supplier, StockReceipt(+Line)
│  ├─ sales/       Bill, BillItem, Payment, HeldBill, Return(+Item), batch upload, lookup
│  ├─ shifts/      Shift
│  ├─ reports/     aggregate tables, rollup command, report endpoints
│  └─ audit/       ActivityLog (append-only), event upload, log endpoints
├─ deploy/       docker-compose, nginx, pgbouncer, backup scripts
└─ scripts/      seed_sample_data.py, loadtest/ (Locust)

poc-frontend/                    React Router 7 (SPA mode), TypeScript strict, Tailwind, Dexie
├─ README.md, package.json, tsconfig.json, vite.config.ts, react-router.config.ts (ssr: false),
│  eslint and prettier config, vitest.config.ts
├─ docs/         API_CONTRACT.md (copy) · design/tokens.md
├─ public/       manifest, icons
└─ app/          tests sit next to the code they cover
   ├─ root.tsx, routes.ts, i18n/ (English strings, one layer)
   ├─ domain/          money, bill totals, one row per product, bill number, return refund, shift totals, PIN delay
   ├─ use_cases/       activate counter, sign in, add item, complete bill, hold bill, sync catalogue and people,
   │                   upload outbox, process return, close shift
   ├─ infrastructure/  API client, Dexie schema and repositories, print, clock offset, storage
   ├─ routes/{auth,admin,pos}/
   ├─ components/{ui,admin,pos}/      presentation only
   └─ styles/
```

SPA mode because the cashier PWA must load offline. `/admin` and `/pos` share one build; `/pos` is code-split. `API_CONTRACT.md` lives in `poc-backend/docs/` and is copied to `poc-frontend/docs/` in a `docs/` commit whenever it changes.

## 2. Database models (PostgreSQL)

Conventions
- `tenant_id` (not null, first column of every index), `created_at`, `updated_at` on every table.
- Money `numeric(12,2)`, quantities `numeric(12,3)`; the API sends both as strings. Timestamps UTC.
- Client-created records (bills, payments, shifts, held bills, returns) use a **client UUID as primary key**. Others use bigint.
- All queries go through a `TenantManager` filtered by the token's tenant. IDs from the request are never trusted across tenants.
- **No branches table (fixed decision).** Every bill, shift and return stores `counter_id`, so a branch layer can be added later.

**tenants:** name, slug (unique), plan, status, timezone (default Asia/Karachi).
**tenant_settings (1:1):** store_name, phone, address, logo, currency (PKR only, fixed, display only), tax_rate (**a percent**, 0 to 100 inclusive: `17.00` means 17%, not a fraction like 0.17; `numeric(5,2)`, default `0.00`; sent as a string), prices_include_tax, block_when_out_of_stock (default false), receipt_paper_mm (58/80), receipt_header, receipt_footer, receipt_show_barcode.

**counters:** name (editable), code (3 digits, unique per tenant, used in bill numbers, locked after the counter's first bill), is_active, last_bill_seq (highest sequence the server has seen, raised with `GREATEST` in the bill-batch transaction; 0 if none).
**device_codes:** counter_id, code_hash, expires_at, used_at, revoked_at, created_by. Format `XXXX-XXXX` (8 characters, uppercase letters and digits without 0, O, 1, I, L; example `K7M4-Q92R`), single use, 15-minute expiry, stored hashed. A new code revokes any earlier unused code for that counter.
**devices:** counter_id, token_hash (SHA-256 of the opaque token), app_version, last_seen_at, unsynced_count (from the last heartbeat, nullable), revoked_at, revoked_by. A counter has at most one live (non-revoked) device. `device_codes.code_hash` is an HMAC-SHA256 keyed with the server secret, because 8-character codes are low entropy.

**users:** full_name, role (owner, manager, cashier), email (nullable, owner and manager), username (nullable, owner and manager), password_hash (owner and manager only), pin_hash (cashiers only, 4 digits `0-9`, Argon2), pin_verifier (cashiers only; the offline PIN check sent to counters, format below), default_counter_id (a UI default only, never a restriction), is_active, last_active_at. Cashiers have no email, username or password.
- Unique: (tenant, lower(email)) WHERE email IS NOT NULL; (tenant, lower(username)) WHERE username IS NOT NULL; **(tenant, lower(full_name)) WHERE role = cashier** (includes deactivated cashiers, so history never becomes ambiguous). Names are trimmed and inner spaces collapsed before saving and matching.
- **`pin_verifier` format:** `pbkdf2_sha256$<iterations>$<salt>$<hash>`. PBKDF2-HMAC-SHA256 over the 4-digit PIN (UTF-8), salt used as its UTF-8 string, 32-byte derived key, `<hash>` in standard base64 with padding. Iterations are 600,000 today, so always read them from the string. Written whenever a PIN is set or reset. WebCrypto check: `deriveBits({name:"PBKDF2", hash:"SHA-256", salt, iterations}, key, 256)`, then compare base64. Test vector (RFC 7914): PIN `passwd`, salt `salt`, 1 iteration → `pbkdf2_sha256$1$salt$VawEblbjCJ/sFpHCJUS2BflBhSFt3gRl5oudV8INrLw=`.
- No approval PIN, approver flag or permission flags. In the POC the role decides everything; the manager role has no screens.
**pin_delays:** counter_id, user_id (cashier), fail_count, next_allowed_at, last_failed_at, unlocked_at. Unique (tenant, counter, user). State for the cashier PIN delay (section 4.1).

**categories:** name, tint (design color key), sort_order, is_active. Unique (tenant, name).
**products:** barcode, name, name_lc, category_id, unit (pcs, kg, litre, pack), price, cost, low_stock_alert, is_archived, archived_at, archived_by. Index `updated_at` for sync.
**price_history:** product_id, old_price, new_price, changed_by, source (edit, import; bulk later), changed_at. Also used to find the price in force at a past time.

**stock_levels:** product_id, qty (may go negative), updated_at. Unique (tenant, product).
**stock_movements (append-only):** product_id, type (sale, return, receive, adjust_add, adjust_remove, count_correction; void later), qty_delta, ref_type, ref_id, reason (received, damaged, expired, stolen_lost, count_correction), note, user_id, occurred_at.
**suppliers:** name, phone.
**stock_receipts:** supplier_id, invoice_no, delivery_date, total_cost, status (draft, confirmed), confirmed_by. **stock_receipt_lines:** receipt_id, product_id, qty, unit_cost, prev_cost. Confirming adds stock, sets `products.cost` to the new cost and adds `total_cost` to `purchases_daily` for `delivery_date`. A confirmed receipt cannot be edited.

**bills (client UUID pk):** counter_id, shift_id, cashier_id, bill_no (unique per tenant), sold_at (device time, skew-corrected), received_at (server), item_count, subtotal, tax_amount, rounding, total, status (paid, partially_refunded, refunded; voided later), flags text[] (price_mismatch, clock_skew, negative_stock), rolled_up_at, device_id, app_version. Phase 2 columns created now, nullable: discount_type, discount_value, discount_amount, customer_id.
**bill_items:** bill_id, line_no, product_id, name_snapshot, barcode_snapshot, qty, unit_price, cost_snapshot, line_total, sold_at. **One row per product per bill** (unique bill_id + product_id).
**payments (client UUID pk):** bill_id, method (cash, card, wallet), amount, tendered (cash), change_given (cash), reference (optional). POC rule: exactly one row per bill. The table exists so split payment needs no migration.
**held_bills (client UUID pk):** counter_id, shift_id, cashier_id, title, payload jsonb, total, status (held, recalled, deleted, abandoned).

**returns (client UUID pk):** counter_id, shift_id, cashier_id (processed_by), original_bill_no (as typed, nullable), original_bill_id (set when the bill is found), reason (expired_damaged, wrong_item, changed_mind, price_error), restock (bool), refund_method (cash, card, wallet), **paid_from_drawer (bool, true only when refund_method = cash)**, refund_total (the amount paid out, as sent by the counter), returned_at (device time, skew-corrected), received_at, flags text[] (over_return, item_not_on_bill, bill_not_found, price_mismatch, clock_skew), rolled_up_at, device_id.
**return_items:** return_id, product_id, bill_item_id (nullable; set when the bill is found and the product is on it), qty, price_source (paid, current), unit_price, refund_amount, tax_refund, cost_snapshot (the bill item's cost when found, otherwise the product's cost at return time).

**shifts (client UUID pk):** counter_id, cashier_id, opened_at, closed_at, opening_cash, counted_cash, expected_cash (server-computed), difference, unsynced_at_close, summary jsonb, status (open, closed). Partial unique: one open shift per counter.
Expected cash = opening + cash amounts from sales (not tendered) − `refund_total` of returns with `paid_from_drawer = true` and `shift_id` = this shift. Card and wallet refunds never touch the drawer. Cash drops are not in the POC. `summary` includes refund count and amount.

**reports (pre-summed; nothing reads raw bills):**
- `sales_hourly` (tenant, counter, hour_start): bills, items, gross, tax, cash, card, wallet, cost, refund_count, refund_amount, refund_cost_recovered.
- `sales_daily` (tenant, local_date): the same columns without the counter. Feeds the dashboard series and the Money trail.
- `sales_daily_product` (tenant, local_date, product): qty, revenue, cost, returns_qty, refund_amount.
- `sales_daily_cashier` (tenant, local_date, cashier): bills, revenue, refund_count, refund_amount. Rows for deactivated cashiers stay.
- `purchases_daily` (tenant, local_date, amount): filled when a stock receipt is confirmed, by `delivery_date`.
- Rules: **sales figures are gross; refunds are always shown separately.** Net = sales − refunds − stock bought (Money trail). **Gross profit** = sales profit − (refund_amount − cost recovered), where cost recovered is `cost_snapshot x qty` only for restocked returns, so a return that is not restocked is a full loss. Returns are bucketed by `returned_at`, not the original sale time. Local dates use the tenant timezone.

**audit.activity_log (append-only):** user_id, action, entity_type, entity_id, before jsonb, after jsonb, detail, device_id, client_event_id (nullable, unique per tenant, for idempotent event upload), occurred_at (original time, kept for offline actions), ip. A database trigger rejects UPDATE and DELETE; the app role has INSERT and SELECT only.
- Normal changes are written in the **same transaction** as the change.
- **Failures are written outside the request transaction** (separate connection or autocommit) so a 401, 429 or rollback cannot erase them: PIN and password failures, throttled sign-ins, failed activation attempts.
Actions recorded: price change (old, new), product create and archive, stock receive and adjust (with reason), return and refund (cashier, items, amount, reason), held bill deleted, shift open and close (with cash difference), staff change, settings change, login and PIN failures, PIN unlock, counter created, counter activated, counter deactivated.
Owner-only read. The admin screen and its endpoints are in the POC (section 4.8).

## 3. Key indexes

| Table | Index | Why |
|---|---|---|
| products | unique (tenant, barcode) WHERE NOT is_archived | Barcode lookup, no live duplicates |
| products | (tenant, updated_at, id) | Sync |
| products | GIN trigram on name_lc | Admin search |
| products | (tenant, category_id) | Category filter |
| stock_levels | unique (tenant, product) | Lookup, low and out lists |
| stock_movements | (tenant, product, occurred_at DESC); unique (tenant, ref_type, ref_id, product) WHERE type = sale; unique (tenant, ref_type, ref_id, product) WHERE type = return | History; retry-safe decrement and restock |
| bills | unique (tenant, bill_no); (tenant, sold_at DESC, id); (tenant, cashier_id, sold_at); (tenant, received_at) WHERE rolled_up_at IS NULL | Idempotency, sales list, rollup |
| bill_items | (tenant, bill_id); unique (bill_id, product_id) | Detail, one row per product |
| counters | unique (tenant, code) | Duplicate-code error |
| device_codes | unique (code_hash); (tenant, counter_id, expires_at DESC) | Activation lookup, current code per counter |
| devices | unique (counter_id) WHERE revoked_at IS NULL | One live device per counter |
| shifts | unique (counter_id) WHERE status = open | One open shift |
| returns | (tenant, original_bill_id); (tenant, shift_id); (tenant, cashier_id, returned_at); (tenant, received_at) WHERE rolled_up_at IS NULL | Over-return check, shift refunds, by-cashier report, rollup |
| return_items | (tenant, return_id); (tenant, bill_item_id); (tenant, product_id) | Returned-quantity check |
| pin_delays | unique (tenant, counter_id, user_id) | Delay lookup |
| users | unique (tenant, lower(email)) and (tenant, lower(username)), both partial; unique (tenant, lower(full_name)) WHERE role = cashier | Sign-in, unique names |
| sales_daily, purchases_daily | unique (tenant, local_date) | Money trail |
| activity_log | (tenant, occurred_at DESC, id DESC); (tenant, action, occurred_at DESC, id DESC); (tenant, entity_type, entity_id); unique (tenant, client_event_id) WHERE client_event_id IS NOT NULL | Log filters and paging, idempotent upload |

## 4. API contract

Base `/api/v1`, JSON, `Authorization: Bearer <access>`.
Roles: **O** owner, **M** manager (in the model, no POC screens), **C** cashier, **D** activated counter device (before anyone signs in), **Any** signed-in.

Conventions
- Errors: `{ "error": { "code", "message", "fields": { "name": ["msg"] } } }`, HTTP 400/401/403/404/409/410/429.
- Lists: `?page=&page_size=` for small tables; **keyset cursor** for bills and the activity log.
- Idempotency: client UUIDs in bodies; `Idempotency-Key` header on Admin writes that must not run twice (receipt confirm, stock adjust).
- Tokens: access 15 min; rotating refresh. Counter sessions get a 30-day sliding refresh so a long outage never locks a counter out.
- **Counter PC credentials.** A **D** call sends the opaque device token as `Authorization: Device <device_token>`. `/auth/pin-login` issues a cashier pair whose tokens carry a `device_id` claim, so **C** calls send only `Authorization: Bearer <access>`. Endpoints marked D, C accept either. The server checks the PC on every request and on `/auth/refresh`. A revoked PC gets 401 `device_revoked` for its device token, its cashiers' access tokens and their refresh tokens. An unknown or malformed device token gets 401 `device_invalid`. The refresh of a counter session keeps the `device_id` claim and slides another 30 days. Owner and manager tokens have no `device_id` and a 7-day rotating refresh.
- **Optional fields** (marked `?` in responses) are always present and `null` when there is no value; they are never left out.
- **The server never rejects a sale or return that already happened.** Anomalies are accepted and flagged. Only malformed or foreign-tenant data is rejected. The one exception is a **deactivated counter PC, which is refused everywhere** (401 `device_revoked`).

### 4.1 Auth and devices
| Method | Path | Roles | Request → Response |
|---|---|---|---|
| POST | /auth/login | public | `{login, password}` (`login` is an email or username, case-insensitive) → `{access, refresh, user, tenant, landing:"admin"}`. Owner and manager only; a cashier gets the same 401 `invalid_credentials`. Rate limited per IP and login (429 with `retry_after`); accounts are never locked |
| POST | /auth/refresh | public | `{refresh}` → `{access, refresh}` |
| POST | /auth/logout | Any | `{refresh}` → 204 |
| GET | /me | Any | → `{user, tenant, permissions}` |
| POST | /devices/codes | O | `{counter_id}` → 201 `{code:"K7M4-Q92R", expires_at}`. Revokes any earlier unused code for that counter. 409 `counter_active` while the counter has a live PC; 404 `not_found` for a counter not in the tenant. The plain code is returned once |
| DELETE | /devices/codes/{counter_id} | O | Revokes the unused code without making a new one → 204 (also 204 when there is none; 404 `not_found` for a counter not in the tenant) |
| POST | /devices/activate | public | `{code, app_version}` → `{device_token, counter:{id, name, code}}`. Case, hyphens and spaces ignored. Errors: 400 `code_invalid` (unknown, malformed, or revoked or replaced by a newer code), 410 `code_expired`, 409 `code_used`, 409 `counter_active` (the counter gained a live PC meanwhile). Rate limited per IP (10 attempts per 15 min, then 429 `activation_throttled` with `retry_after`). Logs `counter_activated`; failures on a known code are logged as `activation_failed` |
| POST | /auth/pin-login | D | `{user_id, pin}` → `{access, refresh, user}`. Cashiers only. The counter always comes from the device token. Wrong PIN: 401 `invalid_pin`; when that wrong PIN starts a delay, the 401 also carries `retry_after` (and a `Retry-After` header) so the keypad can start the countdown at once. During a delay: 429 `pin_throttled` with `retry_after`. An unknown, deactivated, owner, manager or other-tenant `user_id` gets the same 401 `invalid_pin` and never starts a delay. Failures are logged as `pin_failure` and delayed tries as `pin_throttled` |
| GET | /pos/bootstrap | D, C | → `{counter:{id, name, code}, settings{...}, last_bill_seq, roster[], server_time}`. `settings` is the whole `/tenant/settings` object (store profile, currency, `tax_rate` as a percent string, prices_include_tax, block_when_out_of_stock, receipt fields). `roster` has the `/pos/roster` shape (no verifiers; those come from people sync) |
| GET | /pos/roster | D | → `[{id, full_name, initials}]`. All active cashiers, whatever their default counter |
| GET | /pos/people/sync/ | D, C | `?since=` → `{roster:[{id, full_name, initials, pin_verifier, active, unlocked_at}], next_since}`. Runs with every delta sync, so a deactivated cashier disappears from the counter's Dexie within a minute and an owner unlock reaches the device. Rules below |
| POST | /counters/{id}/heartbeat | D, C | `{unsynced_count, cashier_id?, app_version}` → `{server_time}` (every 15 s; updates `devices.last_seen_at`, `unsynced_count` and `app_version`, and the cashier's `last_active_at`). `{id}` must be this PC's counter (404 `not_found` otherwise). `cashier_id` defaults to the signed-in cashier; a `cashier_id` that is not a cashier of the tenant gives 400 on `cashier_id` |

**People sync rules.**
- `since` is an ISO-8601 UTC time: the previous `next_since`. Missing or `0` means a full sync, which returns active cashiers only.
- A delta returns every cashier changed after `since`, deactivated ones included (`active: false`, `pin_verifier: null`), so the counter removes them.
- `next_since` is the server time minus 60 s, so rows changed in the last minute come again in the next sync. Re-applying a row is harmless, and a change that commits late is never missed.
- `unlocked_at` is the last owner unlock or PIN reset for this cashier **at this counter** (both write it for every counter). The device clears its local delay when `unlocked_at` is later than the delay's start.
- Cashier edits, deactivation, PIN reset and unlock all come through this sync; the heartbeat does not.

**Sign-in flow.** The cashier types a full name. The device trims it, collapses spaces, matches it case-insensitively against the roster in Dexie, and sends the matched `user_id` with the PIN. An unmatched name never reaches the server; the screen says the name was not found.

**Cashier PIN delays.** Wrong PINs are counted per cashier **and counter** in `pin_delays`.
- The first three wrong PINs are free. Each further wrong PIN starts a delay of **30 s, then 1 min, then 5 min**; 5 min stays the maximum. A correct PIN resets the count.
- During a delay the answer is 429 `pin_throttled` with the remaining seconds in `retry_after`, and the keypad shows the countdown. Nothing is disabled, only delayed.
- The delay applies to that cashier at that counter only.
- Offline, the device applies the same schedule from local state in `meta`. `unlocked_at` in `/pos/people/sync/` clears the local delay.
- The owner can clear a delay at any time (`POST /users/{id}/unlock`, 4.2). Owner and manager accounts never use PIN sign-in.
- Failures are written to the activity log outside the request transaction; offline failures arrive through `/audit/events/batch`.
- **Known limit, accepted for the POC:** a colleague at the same counter can keep another cashier delayed with wrong PINs (the unlock is the remedy). Cashier PINs are 4 digits, so a verifier cached on a counter PC can be brute-forced offline. The damage is limited to signing in at that counter, where every action is logged.

### 4.2 Tenant, counters, staff
| Method | Path | Roles | Notes |
|---|---|---|---|
| GET, PATCH | /tenant/settings | O | Store profile, tax, receipt, block-when-out-of-stock. Currency is fixed to PKR. `tax_rate` is a percent string (`"17.00"` = 17%); outside 0 to 100 gives 400 `validation_error` on `tax_rate` |
| GET | /counters | O | → `[{id, name, code, is_active, status:"not_activated"｜"code_ready"｜"activated"｜"deactivated", code_expires_at?, last_seen_at?, app_version?, last_bill_seq, next_bill_no, unsynced_count?, has_open_shift, has_bills}]`. `next_bill_no` is `last_bill_seq + 1` shown as `002-000743` (the server's view; unsynced bills on the PC may already use later numbers). `unsynced_count` is from the last heartbeat. `status`: `activated` when the counter has a live PC, else `code_ready` when it has an unused, unexpired code, else `deactivated` when a PC was revoked, else `not_activated`; `is_active` is the owner's own flag and does not change `status`. `code_expires_at` is set only for `code_ready`; `last_seen_at`, `app_version` and `unsynced_count` come from the live PC, else `null`. `has_bills` is `last_bill_seq > 0` |
| POST | /counters | O | `{name, code}`; 409 `code_exists`; logs `counter_created` |
| PATCH | /counters/{id} | O | Name and active flag. Changing `code` after the first bill: 409 `counter_code_locked` |
| POST | /counters/{id}/deactivate | O | → 204. Revokes the PC's device token and refresh tokens (`devices.revoked_at`); from then on that PC gets 401 `device_revoked`. **409 `shift_open` while the counter has an open shift.** Logs `counter_deactivated`. The counter keeps its code and sequence; the owner can then make a new code for a replacement PC, which continues above `last_bill_seq` |
| GET | /users | O | Filters: `role`, `status` (`active`｜`deactivated`), `counter` (default counter). Paged: `?page=&page_size=` → `{count, results:[{id, full_name, initials, role, email, username, default_counter_id, is_active, last_active_at, pin_delay_until}]}`, ordered by name. `pin_delay_until` is the end of the latest running delay on any counter, else `null` |
| POST | /users | O | Cashier: `{full_name, pin, default_counter_id}`. Owner or manager: `{full_name, email?, username?, password, role}`. 409 `name_exists` (field error on `full_name`) for a duplicate cashier name; 409 `email_exists` or `username_exists` (field error on that field) for an owner or manager login already used in the tenant |
| PATCH | /users/{id} | O | Includes deactivate. Renaming a cashier follows the same unique-name rule (409 `name_exists`); email and username changes give 409 `email_exists` or `username_exists`. Deactivating your own account: 409 `cannot_deactivate_self` (field error on `is_active`) |
| POST | /users/{id}/reset-pin | O | Cashier: → `{pin}` (4 digits, shown once; also clears any delay). 409 `not_a_cashier` for an owner or manager |
| POST | /users/{id}/unlock | O | Cashiers only (409 `not_a_cashier` otherwise). Clears the PIN delay on every counter → 204. Logs `pin_unlock`. No POC screen yet |

An owner's password reset has no endpoint: it is a management command (section 7).

Staff error codes (all use the standard error shape):

| Code | HTTP | When |
|---|---|---|
| `name_exists` | 409 | A cashier full name already used in the tenant (case-insensitive, deactivated cashiers included). Field error on `full_name` |
| `email_exists` | 409 | An owner or manager email already used in the tenant (case-insensitive). Field error on `email` |
| `username_exists` | 409 | An owner or manager username already used in the tenant (case-insensitive). Field error on `username` |
| `cannot_deactivate_self` | 409 | `PATCH /users/{id}` with `is_active: false` on the signed-in user's own account. Field error on `is_active` |
| `not_a_cashier` | 409 | `reset-pin` or `unlock` on an owner or manager (only cashiers have a PIN) |

### 4.3 Catalogue
| Method | Path | Roles | Request → Response |
|---|---|---|---|
| GET | /categories | Any | `[{id, name, tint, product_count}]`, ordered by `sort_order` (new categories go last). `product_count` counts live (not archived) products |
| POST, PATCH | /categories, /categories/{id} | O | `{name, tint}`. `tint` is one of `green, blue, orange, pink, purple, teal, yellow` (the design colour keys). Names are trimmed and unique per tenant ignoring case: 409 `name_exists` (field error on `name`) |
| DELETE | /categories/{id} | O | → 204. 409 `category_has_products` while any product uses it, **archived products included** (move them first) |
| POST | /categories/{id}/move-products | O | `{to_category_id}` → `{moved}`. Moves live and archived products; the target must be another category of the tenant (400 on `to_category_id` otherwise). Moved products reach counters in the next sync |
| GET | /products | O, C | `?search=&category=&stock=all｜low｜out&archived=true｜false&page=&page_size=` → `{count, results:[{id, barcode, name, category:{id, name, tint}, unit, price, cost*, stock, status}]}`. `cost` is left out entirely for C. Sorted by name. `search` matches the name anywhere or the barcode prefix. `archived` defaults to false (live products only). `stock=out` includes negative stock; `stock=low` is above zero and at or under `low_stock_alert`. `status`: `in_stock`, `low`, `out` (zero), `negative` (below zero, allowed and flagged) or `archived` |
| POST | /products | O | `{barcode, name, category_id, unit, price, cost, stock?, low_stock_alert?}` → 201 product detail. `unit` is `pcs｜kg｜litre｜pack`; `barcode` is 1 to 64 characters without spaces; `price`, `cost`, `stock` and `low_stock_alert` are 0 or more. Opening `stock` (default 0) writes the stock level; there is no opening stock movement. 409 `barcode_exists` (field error on `barcode`) while a live product has the barcode. Logs `product_created` |
| GET | /products/{id} | O | Product detail: the list row plus `low_stock_alert`, `is_archived`, `archived_at` |
| PATCH | /products/{id} | O | `barcode, name, category_id, unit, price, cost, low_stock_alert` (any subset; stock is changed only through stock adjust, 4.4). A price change writes price_history and logs `price_changed` (old, new) in the same transaction. 409 `barcode_exists` |
| POST | /products/{id}/archive, /restore | O | → product detail. The "Delete" button archives (logs `product_archived`); archiving twice changes nothing. Restore logs `product_restored` and gives 409 `barcode_exists` while another live product has the barcode |
| GET | /products/by-barcode/{code} | O, C | Live product (list-row shape, no `cost` for C) or 404 `unknown_barcode` (Scan to add) |
| GET | /products/{id}/price-history | O | `[{when, who, old, new}]`, newest first. `who` is the user's full name |
| GET | /products/sync/ | D, C | `?since=<cursor>&page_size=` (1 to 2,000, default 2,000) → `{products:[{id, barcode, name, name_lc, category_id, unit, price, low_stock_alert, is_archived}], categories:[{id, name, tint, sort_order}], next_since, has_more}`. Never sends `cost`. `categories` is always the full list, so a deleted category disappears |
| GET | /stock/sync/ | D, C | `?since=` → `{levels:[{product_id, qty}], next_since}`. Not paged: all changes since the cursor |

**Sync cursor (products and stock).** `next_since` is an **opaque** string: the client stores it and sends it back unchanged, and never parses or edits it. `since=0` (or no `since`) starts a full sync. Rows come in `(updated_at, id)` order, so pages never repeat or skip rows, even when thousands of rows share one timestamp (a bulk import). While `has_more` is true, call again at once with the new `next_since`. On the last page the server steps the cursor back 10 s itself, so rows saved just before a sync and committed just after it are sent next time; re-applying an upsert is harmless. Archived products arrive with `is_archived: true` so counters remove them.

### 4.4 Inventory
| Method | Path | Roles | Request → Response |
|---|---|---|---|
| GET | /stock | O | `?status=all｜low｜out｜negative&search=&page=` |
| POST | /stock/adjust | O | Idempotency-Key. `{product_id, mode:"add"｜"remove"｜"set", qty, reason, note?}` → `{before, after}` (reason required) |
| GET | /stock/movements | O | `?product=&type=&from=&to=&cursor=` |
| GET, POST | /suppliers | O | `{name, phone?}` |
| POST | /stock/receipts | O | `{supplier_id, invoice_no, delivery_date, lines:[{product_id, qty, unit_cost}]}` (draft) |
| POST | /stock/receipts/{id}/confirm | O | Idempotency-Key → adds stock, updates cost, adds to `purchases_daily`, returns `cost_increase_items[]` |
| GET | /stock/receipts, /stock/receipts/{id} | O | History |

### 4.5 Shifts
| Method | Path | Roles | Request → Response |
|---|---|---|---|
| POST | /shifts/open | C, D | `{id(uuid), counter_id, opened_at, opening_cash, cashier_id?}`; 409 `shift_already_open`. D is for a cashier who signed in offline (local PIN verifier) and has no cashier token yet: the device token is sent and `cashier_id` is required, checked as an active cashier of the tenant. With a cashier token, the token's cashier is used. The counter always comes from the PC |
| GET | /shifts/current | C | Open shift for this counter, if any |
| POST | /shifts/{id}/close | C, D | `{closed_at, counted_cash, local_summary, unsynced_count, cashier_id?}` → `{expected_cash, difference, server_summary, mismatch}`. Same D rule as open: with a device token, `cashier_id` is required and checked as an active cashier of the tenant |
| GET | /shifts | O | Filters: date, counter, cashier |
| GET | /shifts/{id}/summary | O, C(own) | Bills, sales by payment type, cash refunds, expected cash |

### 4.6 Bills, held bills and audit events
| Method | Path | Roles | Request → Response |
|---|---|---|---|
| POST | /bills/batch | C, D | See below |
| GET | /bills | O | `?date=&from=&to=&cashier=&payment=&status=&search=<bill no>&cursor=` → `{results:[{id, bill_no, time, cashier, items, payment, total, status}], next_cursor}` |
| GET | /bills/{id} | O | Lines, payment, cashier, counter, returns |
| GET | /bills/lookup | C | `?bill_no=` → `{bill_no, lines:[{product_id, name, qty, unit_price, returnable_qty}]}` or 404 `bill_not_found`. Used by Returns for bills that are not in `recent_bills` (other counters). A 404 does not stop the return (section 4.7) |
| POST | /held-bills/sync | C | `{held:[{id, title, payload, total, status, updated_at}]}` (best-effort mirror; **it never logs deletes**) |
| POST | /audit/events/batch | C, D | See below |

```
POST /bills/batch
Request  { "counter_id": "...", "bills": [ up to 100 of:
  { "id": "uuid", "bill_no": "002000743", "shift_id": "uuid", "cashier_id": 12,
    "sold_at": "2026-09-19T12:47:03Z",
    "items": [ { "line_no": 1, "product_id": 88, "barcode": "8961002300022",
                 "name": "Cooking Oil 1L", "qty": "5.000", "unit_price": "50.00" } ],
    "payment": { "id": "uuid", "method": "cash", "amount": "250.00", "tendered": "500.00", "change_given": "250.00" },
    "totals": { "item_count": 5, "subtotal": "250.00", "tax": "0.00", "rounding": "0.00", "total": "250.00" } } ] }

Response 200 { "server_time": "...", "results": [
  { "id": "uuid", "status": "created" | "duplicate" | "rejected", "bill_no": "...", "flags": [], "errors": [] } ] }
```
- `created` and `duplicate` both mean safe to delete from the device outbox. `rejected` is only for malformed data; the client keeps it and shows a support alert.
- **One row per product.** The client sends merged lines. If a batch repeats a product, the server merges the lines and adds the quantities.
- Each bill runs in its own savepoint. One bad bill never blocks the batch.
- The server recomputes totals from the lines. A mismatch beyond Rs 1 is stored as sent and flagged. A unit price different from the price in force at `sold_at` is flagged `price_mismatch`.
- One transaction per batch: insert bills, items and payments (`ON CONFLICT DO NOTHING` on id), write stock movements, apply one summed `UPDATE` per product in product-id order, raise `counters.last_bill_seq`, write activity rows. Report tables are not touched here.
- Limits: 100 bills per request; 429 with `Retry-After` when busy.

```
POST /audit/events/batch     (C, D)
Request  { "events": [ up to 100 of:
  { "id": "uuid", "action": "pin_failure" | "held_bill_deleted",
    "occurred_at": "2026-09-19T12:40:00Z",
    "entity_type": "held_bill"?, "entity_id": "uuid"?,
    "detail": { "title": "Bill for Ahmed", "total": "1350.00" } } ] }
Response 200 { "results": [ { "id": "uuid", "status": "created" | "duplicate" | "rejected" } ] }
```
- **Whitelisted actions only.** Anything else is `rejected`.
- **The server stamps tenant, user (from the token), device, counter and IP.** The client cannot choose them. `id` becomes `client_event_id`, so retries are safe (`duplicate`). `occurred_at` is kept (skew-corrected).
- **This is the only path that logs held-bill deletes.** The counter queues the event in `audit_outbox` at the moment of deletion.

### 4.7 Returns
A return is a customer bringing back an item they already bought. It is **not** the change handed back at payment. **No PIN and no approval:** any signed-in cashier can process one. The controls are the activity log, the dashboard's refunds today and the Money trail.

```
POST /returns/batch        (C, D, up to 50 per request)
{ "returns": [ { "id": "uuid", "shift_id": "uuid",
    "lines": [ { "product_id": 88, "qty": "2.000" } ],
    "reason": "changed_mind", "restock": true,
    "refund": { "method": "cash" | "card" | "wallet", "amount": "570.00" },
    "original_bill_no": "001000498"?, "returned_at": "2026-09-19T12:52:10Z" } ] }
-> { "server_time": "...", "results": [ { "id": "uuid", "status": "created" | "duplicate" | "rejected",
     "flags": [], "errors": [] } ] }
```
- Idempotent on the UUID. `rejected` is only for malformed or foreign-tenant data. **Business anomalies are accepted and flagged, never rejected.**
- **Refund price.** With no `original_bill_no`, each line is refunded at today's price (the price in force at `returned_at`, from `price_history`). With a bill number, each line that is on the bill is refunded at the price paid. A line not on the bill, or a bill number the server does not know, falls back to today's price.
- **Flags:**
  - `over_return`: the bill was found and the total returned quantity of a product now exceeds the quantity bought.
  - `item_not_on_bill`: a bill number was given, the bill exists, but a returned product is not on it.
  - `bill_not_found`: a bill number was given but the server has no such bill.
  - `price_mismatch`: the server's recomputed total differs from `refund.amount` by more than Rs 1. The amount as sent is stored, because the money has already left the drawer.
  - `clock_skew`: device clock off by more than 5 minutes.
- **Money rules.** Per line: price used x qty, plus tax at the tenant rate when `tax_rate` is above 0 and prices exclude tax (`tax_refund`); the total follows the same whole-rupee rounding as bills. When a bill is found and the return clears its last returnable quantity, the refund is the remaining amount actually paid, rounding included, so refunds add up to the bill total. Each return item stores `cost_snapshot` so profit stays correct.
- **Concurrency.** When a bill is found, the server locks its rows `FOR UPDATE` in bill-id order before it computes returned quantity, so two counters cannot both over-return without one being flagged.
- **One transaction per batch:** insert the return and items (`ON CONFLICT DO NOTHING` on id); if `restock`, write a `return` stock movement (+qty) and one summed stock update per product in product-id order; if the bill was found, set `bills.status` to `partially_refunded` or `refunded`; write the activity-log row (cashier, items, amount, reason). Report tables are not touched here; the rollup applies negative deltas bucketed by `returned_at`.
- **Effects:** cash refunds reduce the shift's expected cash; card and wallet refunds are recorded only (no gateway) and never touch the drawer. Putting an item back in stock is a checkbox, on by default and off for Damaged or expired (the client sets `restock`).
- **On the device:** the counter looks the bill up in `recent_bills` (this counter, last 7 days, a constant). For another counter's bill it calls `GET /bills/lookup` when online. If the bill is not found or the device is offline, the cashier can still proceed at today's price and the server flags it. Returns upload **after** any older unsent bills (same worker, bills first), so a return is never sent before its own bill.

### 4.8 Reports and activity log
| Method | Path | Roles | Notes |
|---|---|---|---|
| GET | /reports/dashboard | O | `?date=` today totals, **refunds today `{count, amount}`**, 7 and 30 day series, category split, top products, low-stock top 5. "Today" uses the tenant timezone |
| GET | /reports/summary | O | `?from=&to=&group=hour｜day｜week` sales, refunds, profit, bills, average bill |
| GET | /reports/categories, /cashiers, /top-products | O | From aggregate tables only |
| GET | **/reports/money** | O | `?from=&to=&group=day｜month` → `{group, periods:[{period, sales_total, sales_cash, sales_card, sales_wallet, refunds_total, refunds_count, stock_bought, net, gross_profit}], totals:{same fields}}`. **Every period in the range is returned, with zeros where nothing happened (so `stock_bought` is 0 on days without a delivery).** `period` is `2026-09-19` or `2026-09`. Limits: 93 days, or 24 months. Reads `sales_daily` and `purchases_daily` only |
| GET | **/reports/refunds-by-cashier** | O | `?from=&to=` → `[{cashier_id, name, is_active, refunds_count, refunds_amount}]`. **Includes deactivated cashiers** (`is_active: false`) |
| POST | /reports/export | O | `{report:"money"｜"refunds_by_cashier"｜"summary"｜..., from, to, format:"csv"}` → `{job_id}`; GET /jobs/{id} |
| GET | /activity-log | O | `?type=all｜price｜refund｜held_bill｜stock｜shift&from=&to=&user=&cursor=` → `{header:{held_bills_deleted_today, refunds_today, price_changes_today}, results:[{id, occurred_at, user, action, detail, flag:"info"｜"review"}], next_cursor}` |
| GET | /activity-log/export | O | CSV for the chosen filters |

Money trail definitions: `net = sales_total − refunds_total − stock_bought`. `gross_profit` follows the profit rule in section 2. Stock adjustments are not money movements and stay in the activity log only.

Activity-log rules:
- **Keyset paging by `(occurred_at, id)`**, newest first. Offline entries arrive late with old timestamps.
- The "today" counts in `header` are computed in the tenant timezone, not UTC.
- `review` flag: **every refund**, any return flagged `over_return`, `item_not_on_bill` or `bill_not_found`, every held bill deleted, and a non-zero cash difference at shift close. Everything else is `info`.
- Refund rows read like "Refund · cashier Zainab · 2 items · Rs 570".

### 4.9 Roles in the POC
| Area | Owner | Cashier | Counter device |
|---|---|---|---|
| Settings, staff, counters, activation codes, PIN unlock | full | no | activate only |
| Products, categories, stock, receipts | full | read products (no cost) | sync only |
| Sales list, reports, Money trail, shifts overview | full | no | no |
| Sell, hold, close own shift | yes | yes | no |
| Return at the counter | no | yes, no PIN | no |
| Activity log | read and export | no | no |
| Upload audit events | no | yes | yes |

The manager role exists in the data model and gets no POC screens.

## 5. Offline design (cashier)

**Dexie stores:** `meta` (device, counter, settings, sync cursors, clock offset, `bill_seq`, local PIN-delay state), `products` (barcode and name_lc indexed, about 5 MB for 18.5k rows), `categories`, `stock`, `users` (roster with PBKDF2 PIN verifiers for offline sign-in, format in section 2; refreshed by `/pos/people/sync/`), `bills_outbox` (payload, status, attempts, next_try_at), `shifts`, `held_bills`, `recent_bills` (this counter, last 7 days, for reprint and returns), `returns_outbox`, `audit_outbox` (offline PIN failures and held-bill deletes; uploaded through `/audit/events/batch`).
The app calls `navigator.storage.persist()` and refuses to sell if storage is not writable.

**Activation:** "Activate this counter" needs internet once. If the server ever answers `device_revoked`, the counter shows a clear "This PC was deactivated" screen and stops selling.

**Barcode lookup:** IndexedDB only, under 50 ms. Never a network call.

**Current bill (billing rules)**
- A scan adds +1 to the existing row for that product; a new row is created only for a product not yet on the bill.
- Row: name, qty, unit price, line total. Qty is editable by typing, and by + and -.
- Header shows the bill number, the item count (sum of quantities) and the grand total.
- Fix mistakes by removing the row or holding the bill.
- One payment method per bill. Change due = received − total (cash only). This is not a return. Pay stays disabled until cash received covers the total.

**Sync**
1. First run: `/products/sync/` pages of 2,000 from `since=0`, bulk-put, then `/stock/sync/`, then `/pos/people/sync/`. Starting a shift is blocked until this completes once.
2. Then: delta sync every 60 s online, on reconnect and on window focus. Archived products are removed locally (a tombstone is kept so held bills still render). Open bills keep the prices they were scanned at. Deactivated cashiers are removed so they cannot sign in.
3. Completed bill: one Dexie transaction writes to `bills_outbox`, decrements local stock and advances `bill_seq`. Then the receipt prints. A sale never waits on the network.
4. Upload: one worker per counter, one batch in flight (up to 50 bills), triggered on completion, every 15 s and on reconnect. Backoff 2 s to 5 min with jitter; honors `Retry-After`. A bill leaves the outbox only after `created` or `duplicate`. Bills go first; returns and audit events follow with the same rules.
5. Heartbeat every 15 s carries `unsynced_count`; the shift screen warns while it is above zero.
6. Clock: `server_time` sets a clock offset. `sold_at` and `returned_at` use corrected time; skew over 5 minutes flags the record.

**Bill numbers (decided):** counter code (3 digits) + per-counter sequence (6 digits), for example `002000743`, shown `002-000743`, printed as Code128 so a receipt can be scanned on Returns. Each counter owns its sequence, so counters never collide. If a device loses its storage, or a replacement PC is activated, `/pos/bootstrap` returns the highest sequence the server has seen and the client continues above it. The UUID stays the real primary key.

**Negative stock (decided):** never block a sale by default. Stock may go below zero (no CHECK constraint, never clamped). Inventory shows a red "negative" status and a "Count correction" fixes it. If the owner turns on "Block a sale when an item is out of stock", counters enforce it against local stock (best effort offline).

**Shift close offline:** allowed with a warning about unsynced sales. The server recomputes from uploaded bills and returns and flags any difference.

**Returns offline:** written to `returns_outbox`, local stock is increased if `restock`, the drawer figure is reduced locally for cash refunds, and the return uploads like a bill.

## 6. Performance plan (about 50,000 bills/day, later)

- Reports never scan raw bills. A rollup job (every 30 s) runs `SELECT ... FOR UPDATE SKIP LOCKED` on bills and returns where `rolled_up_at IS NULL`, adds deltas to `sales_hourly`, `sales_daily`, `sales_daily_product` and `sales_daily_cashier`, and sets `rolled_up_at` in the same transaction. Returns are negative deltas bucketed by `returned_at`; late bills land in the right hour by `sold_at`.
- Job runner: `manage.py run_rollup` loop under systemd with a Postgres advisory lock (no Celery or Redis).
- Bulk inserts, summed stock updates in product-id order, pgbouncer, `synchronous_commit` on for bills.
- Outage recovery: client-side random 0 to 60 s start delay, one batch in flight, jittered backoff. Server: per-tenant rate limit and a separate worker pool for `/bills/batch`.
- Launch unpartitioned; `bill_items.sold_at` is stored so monthly partitioning can be added later.
- Backups: WAL archiving, nightly base backup, monthly restore test, runbook.
- Load test (Locust, after the cashier step): 10 bills/s for 30 min, plus a 16,000-bill burst from 40 simulated counters. Targets: p95 batch upload under 500 ms, zero lost or duplicated bills, rollup lag under 60 s.

## 7. Decisions, defaults and gaps

**Fixed decisions**
Single store (no branches). Roles owner, manager and cashier (the POC uses owner and cashier). Cashier sign-in by typed name and 4-digit PIN on an activated counter; owner and manager by password. Counters set up by a one-time activation code. Returns are simple, with no PIN or approval. Deleting a product archives it. Client-UUID bill ids and bill numbers like `002-000743`. Negative stock is allowed and flagged. PKR only. English first, Urdu and right-to-left later. POC scope is frozen: no discounts, split payment, loyalty, branches, live counters, bulk price update, cash drops, return approval PINs or admin refunds.

**Defaults in force (from the owner's answers; change only if told)**
- Scanner: USB keyboard-wedge. Receipts print with the browser print dialog and 80 mm CSS. Hardware integration comes after the models are known.
- No receipt on a return: refund at today's price. Refund methods: cash from the drawer, card, wallet (card and wallet recorded only).
- No forgot-password flow. The owner resets staff PINs; an owner password reset is a management command (`manage.py reset_owner_password`).
- A confirmed delivery counts as money out on its delivery date (no paid or credit flag).
- Any item is allowed on a return; if it is not on the bill it is refunded at today's price and flagged.
- No month-by-month table or two-month comparison on the Money trail.
- Refunds of deactivated cashiers stay in the by-cashier list.
- Sign-in overlap: the sign-in page is the only place for name and PIN, and the current PIN screen becomes "Start your shift" (opening cash only). **Not confirmed by the owner and not yet changed in the design.** The frontend shell is built from the sign-in page and "Start your shift" stays a placeholder until confirmed.
- Unique cashier full names per tenant, matched case-insensitively against the local roster.
- The basket logo is also the favicon and app icon. The sign-in photo is a placeholder.

**Choices made in this contract, to confirm**
- Three free wrong PINs before the first 30 s delay.
- Cashier names are unique across all cashiers, deactivated ones included.
- A counter with an open shift cannot be deactivated. If a PC is lost with a shift open, the only remedy in the POC is a management command that closes the shift (`manage.py close_shift <id>`, logged), after which the owner can deactivate.
- A deactivated PC is refused everywhere, so bills still unsynced on it cannot upload later. The counters list shows `unsynced_count` so the owner can warn before deactivating.
- Sales are shown gross with refunds separate; net and profit appear on the Money trail.

**Design gaps (not to be invented; the default is what gets built if there is no answer)**

| Gap | Blocks | Default |
|---|---|---|
| Staff: no screens for edit, reset PIN, deactivate confirmation or the cashier unlock action | Step 7 | Edit reuses the Add cashier form; reset PIN shows the new PIN once in a dialog; a plain confirm dialog for deactivate; Unlock is a text button on a delayed cashier row |
| Settings: no deactivate or revoke-code actions on a counter; no "This PC was deactivated" screen | Steps 3 and 7 | Text buttons in the counters table with confirm dialogs; a full-screen message using the sign-in styles |
| Activate: wrong, expired or used code; offline | Step 3 | Inline error under the code field, same wording as the API errors |
| Sign-in: wrong password, wrong PIN, delay countdown, name not found, loading, offline | Step 3 | Inline error text in the small-error style; keypad greyed with a countdown, as in the design's waiting state |
| Start your shift (see Sign-in overlap) | Step 3 and 5 | Placeholder until confirmed |
| End of shift: cash over or short | Step 5 | Difference shown in the warning colours, no extra screen |
| Returns: item not on the entered bill, bill number not found | Step 6 | Inline note "Refunded at today's price", flagged on the server |
| Money trail: by-month view, empty month, custom range | Step 7 | The 12-month chart is the month view; an empty state line; a from and to date pair |
| Empty and error states on every screen; hover and focus states | Each step | One shared empty and error block; hover darkens 8%, gold uses Dark Gold when pressed, 2 px focus ring in the blue |
| No tablet or phone layouts for Admin | Steps 4 and 7 | Desktop first; the sidebar collapses under 1024 px; no dedicated designs |
| Loose (weighed) items, expiry dates, purchase orders, Urdu and right-to-left, vendor console | After the POC | Not built (the vendor console starts as Django Admin) |

Sample data and the 18,462-product set are for the seed script only. The seed script creates a small POC-sized data set by default and the large set behind a flag.

## 8. Changes from v3.1 to v4

**Returns simplified**
1. Removed the approvals table, approval tokens, approval PINs, `POST /approvals`, `POST /me/approval-pin`, admin refund (`POST /bills/{id}/refund`), offline return caps, return-window enforcement and its settings, the `original_not_found` retry, the `approver_verifiers` in bootstrap and people sync, and the flags `offline_approval`, `offline_cap_exceeded`, `approval_mismatch` and `outside_window`.
2. `returns` drops `source`, `approval_id` and the nullable counter and shift. `paid_from_drawer` is true only for cash; card and wallet refunds are recorded only.
3. `POST /returns/batch` uses the simplified body. Refund price is today's price, or the price paid when the bill is found. Flags: `over_return`, `item_not_on_bill`, `bill_not_found`, `price_mismatch`, `clock_skew`. Nothing is rejected for business reasons.
4. `recent_bills` covers this counter and a constant 7 days. Other counters' bills use `GET /bills/lookup`, and a miss does not block the return.
5. Returns upload after older unsent bills, replacing the server-side retry rule.
6. Activity-log Review flags: every refund, `over_return`, `item_not_on_bill`, `bill_not_found`, every deleted held bill, and a non-zero cash difference at shift close. Audit-event actions are now `pin_failure` and `held_bill_deleted`.

**Sign-in and PIN**
7. `POST /auth/login` is for owner and manager only, with an email or username. `users` gains a nullable `email`; cashiers have no username or password.
8. Cashier full names are unique per tenant (case-insensitive, deactivated cashiers included) with a 409 `name_exists` error; the device matches the typed name against Dexie.
9. The 15-minute lockout is replaced by `pin_delays`: three free wrong PINs, then 30 s, 1 min and 5 min per cashier and counter. The server returns `retry_after`, the device computes the same schedule offline, and `POST /users/{id}/unlock` clears it. The old `pin_attempts` table is gone.

**Counters**
10. Deactivate a counter PC (blocked while a shift is open) and revoke or regenerate a code. A deactivated PC gets 401 `device_revoked`.
11. Activation codes: `device_codes` table, `XXXX-XXXX`, hashed, single use, 15 minutes, errors `code_invalid`, `code_expired`, `code_used`, `counter_active`, rate-limited activation.
12. `GET /counters` returns status, last seen, `last_bill_seq` and `next_bill_no`. Duplicate code gives 409 `code_exists`; the code is locked after the first bill.
13. Activity log records counter created, activated, deactivated and PIN unlock.

**Reports**
14. New `sales_daily` and `purchases_daily`; confirming a stock receipt feeds `purchases_daily` in the same transaction.
15. `GET /reports/money?from=&to=&group=day|month` returns every period with zeros filled in (so `stock_bought` is 0 on days without a delivery). `GET /reports/refunds-by-cashier` includes deactivated cashiers. CSV export covers both. The dashboard gains refunds today (count and amount).
16. Sales figures are gross, with refunds shown separately; net and gross profit come from the Money trail rules.

**Other**
17. `users` drops `can_give_discounts`, `can_edit_prices` and `can_refund_void`.
18. Section 1 is rewritten as two repository trees following the clean-architecture layout, and HANDOFF.md is removed from the tree.
19. The header no longer carries a canvas link and now counts 28 boards.
20. Section 7 records the fixed decisions, the defaults from the owner's answers, the choices made here, and the design gaps with their defaults.
21. (26 Sep 2026) Section 4.2 gains a staff error-code table (`email_exists`, `username_exists`, `cannot_deactivate_self`, `not_a_cashier` next to `name_exists`), and `tenant_settings.tax_rate` is stated as a percent from 0 to 100 (`17.00` = 17%).
22. (26 Sep 2026) Written down from the first backend build: counter-PC credentials (`Authorization: Device`, the `device_id` claim, `device_revoked` and `device_invalid`), the `pin_verifier` column and format, people-sync cursor rules, `null` for optional fields, `retry_after` on the wrong PIN that starts a delay, the activation, bootstrap, heartbeat, `/counters` status and `/users` list details, and roles C, D with `cashier_id?` on shift open and close.
23. (26 Sep 2026) Section 4.3 written down from the catalogue build, and the **product and stock sync cursor changed**: `next_since` is now an opaque keyset cursor that the client sends back unchanged, and the server applies the 10 s overlap itself (before, the client subtracted 10 s, which loops forever when more than a page of rows share one 10 s window). Also: category tints, `name_exists` for categories, delete blocked by archived products too, the `/products` filters and `status` values, cost left out for cashiers, the sync payload fields.
