# Product Requirements Document (PRD)

## Original Problem Statement
Create a local proof-of-concept application named **badger-oic-monitor** to monitor 170 mock Oracle Integration Cloud integrations using a React + Vite + TypeScript frontend, FastAPI backend, SQLite database, and Python mock collector worker.

User-selected scope:
- Pages: Executive Overview, Integration List, Integration Detail, and Settings page
- Data refresh: auto-refresh every 30 seconds
- Recommendation panel: top 3 prioritized recommendations
- Docker: not included for MVP
- Benchmark: all key read endpoints + latency report output

## Architecture Decisions
- Frontend built with React Router and TypeScript on Vite for multi-page dashboard navigation.
- Backend implemented with FastAPI and lifecycle-based startup (`lifespan`) to initialize/seed SQLite and backfill trends/alerts if needed.
- SQLite tables: `integrations`, `run_events`, `latency_logs`, `settings`, `admin_users`, `audit_logs`, `trend_snapshots`, `alert_events`.
- OIC data access abstracted via `OICCollectorInterface`; current implementation uses `MockOICCollector`.
- Deterministic recommendation rules engine returns top 3 actions from simulated error signals.
- Middleware logs API latency for monitored endpoints into SQLite for UI + benchmark visibility.
- Settings security uses local admin auth with signed Bearer token, first-run admin bootstrap, and protected settings/audit endpoints.
- Alerting now reads configurable warning/critical thresholds from Settings and applies them to both alert generation and alert feed visibility.
- Auth migrated to cookie-first session model with httpOnly session cookie + CSRF double-submit header checks.
- Repository split initiated: auth and settings/audit persistence moved into dedicated repositories.

## What Has Been Implemented
- Seed generation and load of 170 integrations across projects/domains with simulated health states.
- Simulation of failed instances, connection errors, timeouts, aborted runs, and missed schedules.
- Executive summary API and dashboard with health score, status counts, critical incidents, top failures.
- Integration list API/page with pagination and filters (status, project, domain, search).
- Integration detail API/page with metadata, run history, status panel, and top-3 recommendations.
- Settings authentication flow: first-run create-admin page, login page, protected settings panel, sign-out support.
- Protected settings APIs (`GET/PUT /api/settings`) and auth APIs (`/api/auth/status`, `/api/auth/register-admin`, `/api/auth/login`).
- Audit logging implemented for login attempts, settings updates, and manual collector triggers; UI audit table added.
- Historical trend snapshots (30-day default) via `/api/trends` and dashboard trend panel.
- In-app alert feed with simulated email log fields via `/api/alerts` and acknowledge action endpoint.
- Configurable threshold controls in Settings for issue score, missed schedules, and critical integration count (warning + critical levels).
- Threshold-aware backend alert behavior: collector-generated alerts and dashboard feed filtering both respect saved thresholds.
- Code-quality hardening pass applied: auth register flow variable safety fix, React hook dependency corrections, and test credential env-var migration.
- Frontend token storage removed from app flow; cookie session now primary. Bearer path retained for automated test compatibility.
- Added auth hardening: password complexity enforcement and temporary lockout after repeated failed login attempts.
- Added CSRF protection on state-changing endpoints (settings updates, alert acknowledgement, manual collector trigger).
- API latency logs endpoint + visual latency panels on dashboard/detail.
- Manual mock collector trigger endpoint and standalone worker script (`backend/mock_collector.py`).
- Benchmark script (`scripts/benchmark.py`) covering summary/list/detail plus backend latency log output.
- Documentation updated: README + architecture notes (`docs/ARCHITECTURE.md`).

## Prioritized Backlog
### P0 (Must Have Next)
1. Rotate admin token secret for production-like local environments and add token revocation/expiry refresh controls.
2. Add server-side session invalidation/revocation table for immediate logout across devices.
3. Add CI workflow for pytest + frontend build + lint checks on every change.

### P1 (Should Have)
1. Add alert mute windows and quiet-hours schedules from Settings.
2. Add CSV export for filtered integration table and incident snapshots.
3. Add per-project trend overlays and incident drilldowns.

### P2 (Nice to Have)
1. Add theme density controls for executive vs operations viewing modes.
2. Add per-project drilldown route with SLA summaries.
3. Add side-by-side comparison of current vs previous collector cycle deltas.

## Next Tasks
1. Complete repository decomposition by extracting alerts/integrations domains into smaller repository modules.
2. Add optional webhook adapter (while keeping current email-log mode for local operation).
3. Add password reset and secure account recovery workflow.
