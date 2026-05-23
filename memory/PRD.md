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
- Backend implemented with FastAPI and lifecycle-based startup (`lifespan`) to initialize and seed SQLite.
- SQLite tables: `integrations`, `run_events`, `latency_logs`, `settings`.
- OIC data access abstracted via `OICCollectorInterface`; current implementation uses `MockOICCollector`.
- Deterministic recommendation rules engine returns top 3 actions from simulated error signals.
- Middleware logs API latency for monitored endpoints into SQLite for UI + benchmark visibility.

## What Has Been Implemented
- Seed generation and load of 170 integrations across projects/domains with simulated health states.
- Simulation of failed instances, connection errors, timeouts, aborted runs, and missed schedules.
- Executive summary API and dashboard with health score, status counts, critical incidents, top failures.
- Integration list API/page with pagination and filters (status, project, domain, search).
- Integration detail API/page with metadata, run history, status panel, and top-3 recommendations.
- Settings API/page for future OIC configuration persistence (abstracted, no real OIC connection).
- API latency logs endpoint + visual latency panels on dashboard/detail.
- Manual mock collector trigger endpoint and standalone worker script (`backend/mock_collector.py`).
- Benchmark script (`scripts/benchmark.py`) covering summary/list/detail plus backend latency log output.
- Documentation: setup/testing README and architecture notes (`docs/ARCHITECTURE.md`).

## Prioritized Backlog
### P0 (Must Have Next)
1. Add authentication/role boundaries for settings changes (admin-only write).
2. Add backend validation and guardrails for malformed settings payloads (email/domain constraints).
3. Add CI test workflow to run backend API tests and frontend build checks automatically.

### P1 (Should Have)
1. Add trend charts for status drift over time (hourly/daily aggregation from run history).
2. Add alert rules configuration (threshold-based warning/critical notifications).
3. Add CSV export for filtered integration table and incident snapshots.

### P2 (Nice to Have)
1. Add theme density controls for executive vs operations viewing modes.
2. Add per-project drilldown route with SLA summaries.
3. Add side-by-side comparison of current vs previous collector cycle deltas.

## Next Tasks
1. Introduce auth + audit log for settings updates.
2. Implement historical trend endpoints for charting health trajectory.
3. Add optional notification adapter interfaces (email/webhook) while retaining local-only defaults.
