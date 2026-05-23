# badger-oic-monitor Architecture Notes

## 1) High-level Architecture

The local proof-of-concept is split into four layers:

1. **React + Vite + TypeScript frontend**
   - Executive dashboard
   - Integration list page
   - Integration detail page
   - Settings page
2. **FastAPI backend**
   - Read endpoints for summary, list, detail, and latency logs
   - Settings read/write endpoints
   - Manual mock collection trigger endpoint
3. **SQLite data layer**
   - Integration state and mock run history
   - API latency logs
   - Persisted settings
4. **Mock collector worker**
   - Simulates changing integration health every cycle
5. **Settings security + observability**
   - First-run local admin creation and login
   - Audit logs for login attempts, settings updates, and manual collector triggers
   - Historical trend snapshots and in-app alerts with simulated email logging
   - Configurable warning/critical thresholds for issue score, missed schedules, and critical integration counts

## 2) OIC abstraction strategy

The backend isolates OIC access behind an interface:

- `OICCollectorInterface` defines the behavior for collector cycles.
- `MockOICCollector` is the current implementation.

This allows future replacement with a real OIC connector without changing API routes or frontend contracts.

## 3) Data model

Primary tables:

- `integrations`: current state for 170 integrations
- `run_events`: time-series execution history
- `latency_logs`: endpoint/method/request-latency tracking
- `settings`: future OIC configuration values
- `admin_users`: local admin credentials (hashed password + salt)
- `audit_logs`: security/activity trail
- `trend_snapshots`: daily health distribution snapshots
- `alert_events`: in-app alerts and simulated email notification records

## 4) Monitoring behavior

- Statuses simulated: `healthy`, `warning`, `critical`, `unknown`
- Error signals simulated: failed instances, connection errors, timeouts, aborted runs, missed schedules
- Deterministic recommendation rules return top 3 actions by priority
- API latency is captured via FastAPI middleware and shown in UI + benchmark output

## 5) Benchmarks

`scripts/benchmark.py` exercises key read endpoints:

- `/api/executive-summary`
- `/api/integrations`
- `/api/integrations/{id}`
- `/api/latency-logs`

It reports `avg`, `p95`, and `max` latency.
