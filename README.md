# badger-oic-monitor

Local proof-of-concept dashboard for monitoring **170 mock Oracle Integration Cloud (OIC) integrations** with Badger branding.

## Stack

- Frontend: React + Vite + TypeScript
- Backend: FastAPI
- Database: SQLite
- Worker: Python mock collector

## Features

1. Seeded dataset with 170 integrations across multiple projects and business domains
2. Simulated health states: healthy, warning, critical, unknown
3. Simulated failures: failed instances, connection errors, timeouts, aborted runs, missed schedules
4. Executive dashboard with health score, counts, critical incidents, top failing integrations
5. Integration list and integration detail pages
6. Deterministic rules engine showing top 3 error recommendations
7. API latency logging middleware + UI latency panels
8. Historical health trends (last 30 days) + in-app alert feed with simulated email log output
9. Configurable alert thresholds in Settings (warning/critical for issue score, missed schedules, and critical integration count)
10. Settings authentication with first-run local admin creation + audit logs (settings updates, login attempts, manual collector triggers)
11. Benchmark script for key read endpoints with latency report output
12. Settings page for future OIC connector configuration (kept abstract)
13. Dedicated Security page with one-time password reset codes and server-side session revocation controls

## Project Structure

```bash
/app
├── backend
│   ├── app
│   ├── mock_collector.py
│   ├── requirements.txt
│   └── server.py
├── frontend
│   ├── src
│   ├── package.json
│   └── vite.config.ts
├── docs
│   └── ARCHITECTURE.md
└── scripts
    └── benchmark.py
```

## Local Setup

### 1) Backend

```bash
cd /app/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn server:app --host 0.0.0.0 --port 8001 --reload
```

### 2) Mock Collector Worker (separate terminal)

```bash
cd /app/backend
source .venv/bin/activate
python mock_collector.py
```

### 3) Frontend

```bash
cd /app/frontend
yarn install
yarn dev
```

### 4) Open App

- Frontend: `http://localhost:3000`
- Backend API base: `http://localhost:8001`

## Quick API Checks

```bash
curl -s http://localhost:8001/api/health
curl -s http://localhost:8001/api/executive-summary
curl -s "http://localhost:8001/api/integrations?limit=5&offset=0"
curl -s http://localhost:8001/api/auth/status
```

## First-Run Settings Access

1. Open the **Settings** page in the frontend.
2. If no admin exists, create the first local admin account.
3. Use those credentials for future login to protected settings and audit logs.
4. Auth now uses httpOnly session cookies + CSRF header protection for state-changing requests.

## Running Authenticated Backend Tests

```bash
TEST_ADMIN_EMAIL=admin@badger.local TEST_ADMIN_PASSWORD='YourStrongPassword!' pytest /app/backend/tests -q
```

## Run Benchmark

```bash
cd /app/backend
source .venv/bin/activate
python /app/scripts/benchmark.py --base-url http://localhost:8001/api --runs 10
```

The benchmark reports average, p95, and max latency for summary, list, and detail endpoints, and prints recent backend latency logs.

## Architecture Notes

See `docs/ARCHITECTURE.md`.

