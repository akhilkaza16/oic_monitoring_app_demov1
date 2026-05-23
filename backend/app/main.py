from __future__ import annotations

import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware

from app.database import init_database
from app.models import (
    ExecutiveSummaryResponse,
    IntegrationDetailResponse,
    IntegrationListResponse,
    LatencyLog,
    SettingsPayload,
)
from app.repository import OICRepository
from app.services.oic_interface import MockOICCollector, OICCollectorInterface
from app.services.rules_engine import build_recommendations

repository = OICRepository()
collector: OICCollectorInterface = MockOICCollector(repository)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_database()
    repository.seed_if_empty(total=170)
    yield


app = FastAPI(title="badger-oic-monitor", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def api_latency_middleware(request: Request, call_next):
    start_time = time.perf_counter()
    response = await call_next(request)
    latency_ms = (time.perf_counter() - start_time) * 1000
    response.headers["X-Latency-Ms"] = f"{latency_ms:.2f}"

    if request.url.path.startswith("/api/"):
        repository.log_latency(
            endpoint=request.url.path,
            method=request.method,
            latency_ms=latency_ms,
        )

    return response


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "badger-oic-monitor-backend"}


@app.get("/api/executive-summary", response_model=ExecutiveSummaryResponse)
def executive_summary() -> ExecutiveSummaryResponse:
    summary = repository.get_executive_summary()
    return ExecutiveSummaryResponse(**summary)


@app.get("/api/integrations", response_model=IntegrationListResponse)
def list_integrations(
    status: str | None = Query(default=None),
    project: str | None = Query(default=None),
    business_domain: str | None = Query(default=None),
    search: str | None = Query(default=None),
    limit: int = Query(default=40, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> IntegrationListResponse:
    total, items = repository.list_integrations(
        status=status,
        project=project,
        business_domain=business_domain,
        search=search,
        limit=limit,
        offset=offset,
    )
    return IntegrationListResponse(total=total, limit=limit, offset=offset, items=items)


@app.get("/api/filter-options")
def filter_options() -> dict[str, list[str]]:
    return repository.get_filter_options()


@app.get("/api/integrations/{integration_id}", response_model=IntegrationDetailResponse)
def integration_detail(integration_id: str) -> IntegrationDetailResponse:
    detail = repository.get_integration_detail(integration_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Integration not found")

    integration, endpoint_url, recent_runs = detail
    recommendations = build_recommendations(
        status=integration.status,
        failed_instances=integration.failed_instances,
        connection_errors=integration.connection_errors,
        timeouts=integration.timeouts,
        aborted_runs=integration.aborted_runs,
        scheduled_runs_missed=integration.scheduled_runs_missed,
    )
    return IntegrationDetailResponse(
        integration=integration,
        endpoint_url=endpoint_url,
        recommendations=recommendations,
        recent_runs=recent_runs,
    )


@app.get("/api/latency-logs", response_model=list[LatencyLog])
def latency_logs(
    endpoint: str | None = Query(default=None),
    limit: int = Query(default=40, ge=1, le=200),
) -> list[LatencyLog]:
    rows = repository.get_latency_logs(endpoint=endpoint, limit=limit)
    return [LatencyLog(**row) for row in rows]


@app.get("/api/settings")
def get_settings() -> dict[str, str | int]:
    values = repository.get_settings()
    return {
        "oic_base_url": values.get("oic_base_url", ""),
        "auth_mode": values.get("auth_mode", "OAuth2"),
        "polling_seconds": int(values.get("polling_seconds", "30")),
        "notification_email": values.get("notification_email", ""),
    }


@app.put("/api/settings")
def put_settings(payload: SettingsPayload) -> dict[str, str | int]:
    saved = repository.upsert_settings(payload)
    return {
        "oic_base_url": saved["oic_base_url"],
        "auth_mode": saved["auth_mode"],
        "polling_seconds": int(saved["polling_seconds"]),
        "notification_email": saved["notification_email"],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/api/mock-collector/run")
def run_mock_collector() -> dict[str, int]:
    updated = collector.collect_cycle()
    return {"updated_integrations": updated}
