# CLAUDE.md — badger-oic-monitor

Proof-of-concept dashboard for monitoring Oracle Integration Cloud (OIC) integrations.
Badger Inc. branding. 170 seeded mock integrations. Light-mode only.

---

## Project Structure

```
/
├── backend/
│   ├── app/
│   │   ├── main.py               # All FastAPI route handlers (20+ endpoints)
│   │   ├── models.py             # Pydantic request/response models
│   │   ├── database.py           # SQLite init, SCHEMA_SCRIPT, get_connection()
│   │   ├── repository.py         # Compatibility shim only — do not add logic here
│   │   ├── services/
│   │   │   ├── auth_service.py         # PBKDF2 hashing, custom JWT (base64 + HMAC-SHA256)
│   │   │   ├── rules_engine.py         # Recommendation scoring, top-3 output
│   │   │   ├── webhook_adapter.py      # Outbound webhook with exponential backoff retry
│   │   │   ├── oic_interface.py        # OICCollectorInterface ABC + MockOICCollector
│   │   │   └── mock_data.py            # Seed dataset generator for 170 integrations
│   │   └── repositories/
│   │       ├── integrations_repository.py
│   │       ├── auth_repository.py
│   │       ├── settings_repository.py
│   │       ├── alerts_repository.py
│   │       ├── collector_repository.py
│   │       ├── trends_repository.py
│   │       ├── latency_repository.py
│   │       └── _legacy_monolith_repository.py   # DEAD CODE — never touch
│   ├── mock_collector.py         # Standalone background worker (30s cycle)
│   ├── server.py                 # Entry point: `from app.main import app`
│   ├── requirements.txt
│   └── tests/                   # 7 pytest integration test files
├── frontend/
│   ├── src/
│   │   ├── api.ts                # All API client functions
│   │   ├── types.ts              # 18 TypeScript interfaces
│   │   ├── App.tsx               # React Router configuration
│   │   ├── pages/                # 6 page components
│   │   └── components/           # NavBar, StatusBadge, MetricCard, etc.
│   ├── package.json
│   ├── vite.config.ts
│   └── tsconfig.json
├── scripts/benchmark.py
├── docs/ARCHITECTURE.md
├── design_guidelines.json        # Source of truth for colors, typography, component specs
└── memory/PRD.md
```

---

## Dev Commands

### Backend

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn server:app --host 0.0.0.0 --port 8001 --reload
```

### Mock Collector (separate terminal)

```bash
cd backend
source .venv/bin/activate
python mock_collector.py
```

Runs indefinitely in 30-second cycles. Stop with Ctrl+C.

### Frontend

```bash
cd frontend
yarn install
yarn dev   # Vite on port 3000
```

Frontend type check and production build:

```bash
cd frontend && yarn build   # runs tsc -b then vite build
```

### Tests

Tests require a **running backend**. Pass credentials as env vars:

```bash
TEST_ADMIN_EMAIL=admin@badger.local TEST_ADMIN_PASSWORD='YourStrongPassword!' pytest backend/tests -q
```

Test suite uses `requests` sessions. No frontend tests exist.

### Benchmark

```bash
python scripts/benchmark.py --base-url http://localhost:8001/api --runs 10
```

---

## Environment Variables

Create `backend/.env` (not committed):

```
SQLITE_DB_PATH=/path/to/oic_monitor.db
ADMIN_AUTH_SECRET=some-long-random-secret
ADMIN_TOKEN_TTL_SECONDS=3600
```

Create `frontend/.env` (not committed):

```
REACT_APP_BACKEND_URL=http://localhost:8001
```

`SQLITE_DB_PATH` is **required** — the backend raises `KeyError` on startup without it. `ADMIN_AUTH_SECRET` is required for token creation.

---

## Architecture

### Layer Map

```
Browser → React/Vite (port 3000) → FastAPI (port 8001) → SQLite
                                  ↑
                            mock_collector.py (separate process)
```

### Backend Request Lifecycle

1. `main.py` route handler receives request.
2. Auth helpers `_require_actor_email` / `_optional_actor_email` validate session cookie or Bearer token.
3. CSRF is validated for all state-changing methods (POST/PUT) when using cookie auth.
4. Route delegates to repository classes for DB access.
5. Service-layer functions handle domain logic.
6. Pydantic model returned as JSON response.

### Repository Pattern

All SQLite access goes through repository classes in `backend/app/repositories/`. No DB calls in `main.py` directly. Each repository owns its table(s).

When adding a new feature:
- New route → handler in `main.py`
- New DB query → method in the relevant repository file
- New request/response shapes → Pydantic model in `models.py`

`repository.py` (root shim) exists only to support `mock_collector.py`'s `OICRepository` import. Do not add logic there.

### Service Layer

- `auth_service.py` — PBKDF2 password hashing and custom JWT creation/validation.
- `rules_engine.py` — stateless `build_recommendations()`. Returns `list[Recommendation]` (top 3, sorted by score). Called from the integration detail route only.
- `webhook_adapter.py` — `WebhookAdapter.send_alert_event()` dispatched in a daemon thread from `collector_repository.py`. Retries with exponential backoff. Logs every delivery outcome to `webhook_delivery_logs`.
- `oic_interface.py` — `OICCollectorInterface` ABC. `MockOICCollector` is the only implementation. Swap this to connect real OIC without touching routes.

---

## Database

- SQLite only. Path from `SQLITE_DB_PATH` env var.
- Auto-initialized at startup via `init_database()` in `database.py` (called in FastAPI `lifespan`).
- No migration tool. To add a column, follow the `_ensure_alert_metric_columns()` pattern in `database.py`: check `PRAGMA table_info(table)`, then `ALTER TABLE ADD COLUMN`.
- `CREATE TABLE IF NOT EXISTS` throughout — schema is idempotent on re-run.

### Tables (12 total)

| Table | Purpose |
|---|---|
| `integrations` | Current state of 170 integrations |
| `run_events` | Time-series execution history (pruned after 3 days) |
| `latency_logs` | Per-request latency captured by FastAPI middleware |
| `settings` | Key-value config pairs |
| `admin_users` | Single admin account (email, hashed password, salt) |
| `admin_login_security` | Failed login count and lockout timestamp |
| `admin_sessions` | Active/revoked session records |
| `password_reset_codes` | One-time reset codes with expiry |
| `webhook_delivery_logs` | Outbound webhook attempt outcomes |
| `audit_logs` | Security and activity trail |
| `trend_snapshots` | Daily health distribution snapshots |
| `alert_events` | In-app alerts and simulated email records |

### Getting a connection

```python
from app.database import get_connection

with get_connection() as connection:
    rows = connection.execute("SELECT ...").fetchall()
    connection.commit()  # required for writes
```

`get_connection()` sets `row_factory = sqlite3.Row` — access columns by name. Convert to `dict` with `dict(row)` before returning from a repository.

---

## Health Score Formula

Used in three places: `integrations_repository.py`, `collector_repository.py`, and `trends_repository.py`. Must stay consistent:

```python
weighted = healthy * 1.0 + warning * 0.6 + critical * 0.2 + unknown * 0.4
score = round(weighted / total * 100, 2)
# Returns 0.0 if total == 0
```

Do not alter this formula without updating all three locations.

---

## Authentication & Security

### Session model

- Login sets two cookies: `session_token` (httpOnly, samesite=strict) and `csrf_token` (readable by JS, samesite=strict).
- `session_token` is a custom JWT: `base64url(payload).hmac_sha256_hex(payload)`. Payload contains `sub` (email), `sid` (session UUID), `exp` (Unix timestamp).
- Bearer token accepted for backward compatibility (automated tests use it).

### CSRF

All state-changing endpoints call `_require_actor_email(..., enforce_csrf=True)`. The frontend reads `csrf_token` cookie and sends it as `X-CSRF-Token` header. CSRF is skipped when using Bearer token auth.

### Password rules

- Minimum 8 chars, maximum 128 chars (`AuthPayload`).
- Password reset `new_password` has a minimum of 10 chars (`PasswordResetConfirmPayload`).

### Account lockout

5 failed login attempts → 15-minute lockout. HTTP 423 returned when locked.

### What requires auth

| Endpoint | Auth required |
|---|---|
| `GET /api/settings` | Yes |
| `PUT /api/settings` | Yes + CSRF |
| `GET /api/webhook-delivery-logs` | Yes |
| `GET /api/audit-logs` | Yes |
| `POST /api/mock-collector/run` | Yes + CSRF |
| `POST /api/security/revoke-sessions` | Yes + CSRF |
| `POST /api/alerts/{id}/acknowledge` | Yes + CSRF |
| All other GET endpoints | No auth |

---

## API Conventions

### Backend

- All routes prefixed with `/api/`.
- Errors use `HTTPException` (400 validation, 401/403 auth, 404 not found, 409 conflict, 423 locked).
- Query parameters use FastAPI `Query()` with explicit `ge`/`le` bounds.
- Latency for all `/api/` requests is automatically recorded to `latency_logs` by middleware.

### Complete endpoint list

```
GET  /api/health
GET  /api/auth/status
POST /api/auth/register-admin
POST /api/auth/login
POST /api/auth/logout
POST /api/auth/password-reset/request
POST /api/auth/password-reset/confirm
POST /api/security/revoke-sessions
GET  /api/executive-summary
GET  /api/trends?days=30
GET  /api/alerts?limit=20&include_acknowledged=false
POST /api/alerts/{alert_id}/acknowledge
GET  /api/integrations?status=&project=&business_domain=&search=&limit=40&offset=0
GET  /api/filter-options
GET  /api/integrations/{integration_id}
GET  /api/latency-logs?endpoint=&limit=40
GET  /api/settings
PUT  /api/settings
GET  /api/webhook-delivery-logs?status=all&limit=60
GET  /api/audit-logs?limit=50
POST /api/mock-collector/run
```

### Frontend API client (`frontend/src/api.ts`)

- Single `request<T>()` helper wraps all `fetch` calls.
- Always uses `credentials: 'include'` for cookie handling.
- Automatically reads `csrf_token` cookie and injects `X-CSRF-Token` for POST/PUT/PATCH/DELETE.
- Throws `Error` with message `"<status>: <detail>"` on non-2xx responses.
- All new API calls go in `api.ts`. Do not call `fetch` directly from components or pages.

---

## Frontend Conventions

### Pages (6 total)

| File | Route | Purpose |
|---|---|---|
| `ExecutiveDashboardPage.tsx` | `/` | Health score, status counts, top failing integrations, trend chart |
| `IntegrationsPage.tsx` | `/integrations` | Filterable paginated table |
| `IntegrationDetailPage.tsx` | `/integrations/:integrationId` | Metadata, run history, recommendations |
| `SettingsPage.tsx` | `/settings` | Auth + config form |
| `SecurityPage.tsx` | `/security` | Session revocation, audit log |
| `NotificationsPage.tsx` | `/notifications` | Webhook delivery log |

Adding a new page:
1. Create file under `frontend/src/pages/`.
2. Add `<Route>` to `App.tsx`.
3. Add nav entry to `NavBar.tsx`'s `navItems` array.

### TypeScript

- All shared types live in `types.ts`. The 18 interfaces mirror the Pydantic models in `models.py` — keep them in sync.
- `IntegrationStatus = "healthy" | "warning" | "critical" | "unknown"` is the canonical status union.
- TypeScript errors surface via `yarn build`. No unit test framework configured.

### Auto-refresh

Pages use `setInterval` inside `useEffect` with a 30-second interval. Always clear the interval in the effect cleanup function.

### Testing attributes

All interactive elements must have `data-testid` attributes (e.g., `data-testid="nav-settings-link"`, `data-testid="integration-row-{id}"`).

---

## Design System

Source of truth: `design_guidelines.json`.

### Colors

| Token | Hex | Usage |
|---|---|---|
| Badger Green | `#019581` | Nav background, buttons, table headers |
| Badger Green Dark | `#016B5E` | Section headings |
| Background | `#F9FAFB` | Page background |
| Surface | `#FFFFFF` | Cards, panels |
| Border | `#E5E7EB` | Card and table borders |
| Critical | `#EF4444` | Status critical |
| Warning | `#F59E0B` | Status warning |
| Success | `#10B981` | Status healthy |
| Info | `#3B82F6` | Info/blue accents |
| Unknown | `#6B7280` | Status unknown / muted text |

### Typography

- Headings: Arial, Helvetica, sans-serif. Bold.
- Body: system-ui, -apple-system, sans-serif.
- Mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace.

### Icons

Use `@phosphor-icons/react` exclusively (already installed).

```tsx
import { ChartBar } from "@phosphor-icons/react";
<ChartBar size={24} weight="duotone" />
```

### Tailwind utility patterns

```
Primary button:   bg-[#019581] hover:bg-[#017d6c] text-white font-medium rounded-md px-4 py-2
Secondary button: bg-white border border-gray-300 hover:bg-gray-50 text-gray-700 font-medium rounded-md px-4 py-2
Danger button:    bg-red-500 hover:bg-red-600 text-white font-medium rounded-md px-4 py-2
Card:             bg-white border border-gray-200 rounded-md shadow-sm p-4 md:p-6
Table header:     bg-[#019581] text-white font-medium text-sm tracking-wider
```

Layout archetype: "Control Room" — dense, high-information, light mode only. **No dark mode.**

---

## Mock Collector Behavior

- `mock_collector.py` is a standalone process — it does not run inside the FastAPI server.
- Each 30-second cycle picks ~34 random integrations and mutates their status/error counts probabilistically.
- Alerts fire when issue score or missed schedule counts cross configured thresholds. Duplicate suppression: no alert for the same `integration_id` + `metric_type` within a cooldown window (45 min for issue score, 60 min for others).
- Webhooks fire in daemon threads from `collector_repository.py`. Failures are caught silently.
- `/api/mock-collector/run` triggers a manual cycle (requires auth + CSRF).
- `run_events` rows older than 3 days are pruned each cycle.

---

## Settings Key Reference

Settings stored in `settings` table as string key-value pairs:

```
oic_base_url
auth_mode
polling_seconds
notification_email
threshold_issue_score_warning / threshold_issue_score_critical
threshold_missed_schedules_warning / threshold_missed_schedules_critical
threshold_critical_integrations_warning / threshold_critical_integrations_critical
webhook_enabled              ("true" / "false" strings)
webhook_url
webhook_bearer_token
webhook_max_retries
webhook_initial_backoff_seconds
webhook_timeout_seconds
```

When adding new settings keys: update `settings_repository.py`, `main.py` deserialization, `SettingsPayload` in `models.py`, and its TypeScript mirror in `types.ts`.

---

## What NOT to Do

- **Do not use `_legacy_monolith_repository.py`** — frozen dead code.
- **Do not add logic to `repository.py`** (the root shim).
- **Do not add an ORM** — all DB access uses raw `sqlite3`.
- **Do not add linters or formatters** (ESLint, Prettier, Black, Ruff) without explicit user approval.
- **Do not add Docker or CI** without explicit user approval.
- **Do not commit `.env` files.**
- **Do not call `fetch` directly in components** — use `request<T>()` in `api.ts`.
- **Do not add dark mode.**
- **Do not bypass CSRF** on mutating endpoints.

---

## Common Patterns

### Adding a protected backend endpoint

```python
# main.py
@app.post("/api/some-action")
def some_action(
    request: Request,
    authorization: str | None = Header(default=None),
    x_csrf_token: str | None = Header(default=None),
) -> dict[str, str]:
    actor = _require_actor_email(request, authorization, csrf_header=x_csrf_token, enforce_csrf=True)
    result = some_repository.do_thing()
    settings_repository.log_audit(actor_email=actor, action_type="thing_done", target="thing", details="")
    return {"status": "ok"}
```

### Adding a public GET endpoint

```python
@app.get("/api/some-data", response_model=list[SomeModel])
def some_data(limit: int = Query(default=20, ge=1, le=200)) -> list[SomeModel]:
    rows = some_repository.get_data(limit=limit)
    return [SomeModel(**row) for row in rows]
```

### Adding a repository method

```python
def get_data(self, *, limit: int) -> list[dict]:
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT ... FROM some_table ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]
```

### Adding a frontend API function

```typescript
// api.ts
export function getSomeData(limit = 20): Promise<SomeType[]> {
  return request<SomeType[]>(`/api/some-data?limit=${limit}`);
}
```

### Schema migration (no tool)

```python
# In database.py — follow the _ensure_alert_metric_columns() pattern
def _ensure_new_column(connection: sqlite3.Connection) -> None:
    existing = {row[1] for row in connection.execute("PRAGMA table_info(table_name)").fetchall()}
    if "new_column" not in existing:
        connection.execute("ALTER TABLE table_name ADD COLUMN new_column TEXT")

# Call from init_database() after executescript(SCHEMA_SCRIPT)
```

---

## Pitfalls

- **`SQLITE_DB_PATH` missing at import time** — `database.py` reads the env var at module level. Importing any `app.*` module without it raises `KeyError` immediately.
- **SQLite `commit()` required** — `get_connection()` does not auto-commit. Call `connection.commit()` after all writes.
- **`webhook_enabled` is a string** — stored as `"true"` / `"false"`. Read with `settings.get("webhook_enabled", "false").lower() == "true"`.
- **Numeric settings are strings** — always use `_to_int()` / `_to_float()` helpers from `main.py` when reading settings values.
- **CSRF in browser vs tests** — tests use Bearer tokens (CSRF skipped). Browser sessions use cookies and require `X-CSRF-Token`. If a protected endpoint returns 403 in the browser but passes in tests, the frontend is missing the CSRF header.
- **Password reset min length is 10**, not 8 — `PasswordResetConfirmPayload.new_password` has `min_length=10`.
- **`mock_collector.py` uses `OICRepository` from `repository.py`** — intentional; do not refactor without also updating `mock_collector.py`.
