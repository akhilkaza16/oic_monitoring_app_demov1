from __future__ import annotations

import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware

from app.database import init_database
from app.models import (
    AlertEvent,
    AuditLogEntry,
    AuthPayload,
    AuthResponse,
    AuthStatusResponse,
    ExecutiveSummaryResponse,
    IntegrationDetailResponse,
    IntegrationListResponse,
    LatencyLog,
    SettingsPayload,
    TrendSnapshot,
)
from app.repository import OICRepository
from app.services.auth_service import create_token, validate_token
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


def _read_bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    if not authorization.startswith("Bearer "):
        return None
    return authorization.replace("Bearer ", "", 1).strip()


def _optional_actor_email(authorization: str | None) -> str | None:
    token = _read_bearer_token(authorization)
    if not token:
        return None
    try:
        return validate_token(token)
    except ValueError:
        return None


def _require_actor_email(authorization: str | None) -> str:
    token = _read_bearer_token(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="Authorization token required")
    try:
        return validate_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "badger-oic-monitor-backend"}


@app.get("/api/auth/status", response_model=AuthStatusResponse)
def auth_status(authorization: str | None = Header(default=None)) -> AuthStatusResponse:
    actor = _optional_actor_email(authorization)
    return AuthStatusResponse(has_admin=repository.has_admin_user(), authenticated_email=actor)


@app.post("/api/auth/register-admin", response_model=AuthResponse)
def register_admin(payload: AuthPayload) -> AuthResponse:
    if repository.has_admin_user():
        repository.log_audit(
            actor_email=payload.email.lower().strip(),
            action_type="admin_register_rejected",
            target="admin_users",
            details="Registration attempt rejected because admin already exists",
        )
        raise HTTPException(status_code=409, detail="Admin is already configured")

    try:
        email = repository.create_first_admin(email=payload.email, password=payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    repository.log_audit(
        actor_email=email,
        action_type="admin_registered",
        target="admin_users",
        details="First admin account created from settings page",
    )
    return AuthResponse(token=create_token(email), email=email)


@app.post("/api/auth/login", response_model=AuthResponse)
def login_admin(payload: AuthPayload) -> AuthResponse:
    is_valid = repository.verify_admin_credentials(email=payload.email, password=payload.password)
    email = payload.email.lower().strip()

    repository.log_audit(
        actor_email=email,
        action_type="login_success" if is_valid else "login_failed",
        target="admin_users",
        details="Admin login attempt",
    )
    if not is_valid:
        raise HTTPException(status_code=401, detail="Invalid admin credentials")

    return AuthResponse(token=create_token(email), email=email)


@app.get("/api/executive-summary", response_model=ExecutiveSummaryResponse)
def executive_summary() -> ExecutiveSummaryResponse:
    summary = repository.get_executive_summary()
    return ExecutiveSummaryResponse(**summary)


@app.get("/api/trends", response_model=list[TrendSnapshot])
def trend_snapshots(days: int = Query(default=30, ge=7, le=90)) -> list[TrendSnapshot]:
    rows = repository.get_trend_snapshots(days=days)
    return [TrendSnapshot(**row) for row in rows]


@app.get("/api/alerts", response_model=list[AlertEvent])
def alerts(
    limit: int = Query(default=20, ge=1, le=200),
    include_acknowledged: bool = Query(default=False),
) -> list[AlertEvent]:
    rows = repository.get_alerts(limit=limit, include_acknowledged=include_acknowledged)
    return [AlertEvent(**row) for row in rows]


@app.post("/api/alerts/{alert_id}/acknowledge")
def acknowledge_alert(alert_id: int, authorization: str | None = Header(default=None)) -> dict[str, str]:
    actor = _require_actor_email(authorization)
    updated = repository.acknowledge_alert(alert_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Alert not found")
    repository.log_audit(
        actor_email=actor,
        action_type="alert_acknowledged",
        target=f"alerts/{alert_id}",
        details="Acknowledged in-app alert",
    )
    return {"status": "acknowledged"}


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
def get_settings(authorization: str | None = Header(default=None)) -> dict[str, str | int]:
    _require_actor_email(authorization)
    values = repository.get_settings()
    return {
        "oic_base_url": values.get("oic_base_url", ""),
        "auth_mode": values.get("auth_mode", "OAuth2"),
        "polling_seconds": int(values.get("polling_seconds", "30")),
        "notification_email": values.get("notification_email", ""),
    }


@app.put("/api/settings")
def put_settings(payload: SettingsPayload, authorization: str | None = Header(default=None)) -> dict[str, str | int]:
    actor = _require_actor_email(authorization)
    saved = repository.upsert_settings(payload)
    repository.log_audit(
        actor_email=actor,
        action_type="settings_updated",
        target="settings",
        details="Updated OIC monitoring settings",
    )
    return {
        "oic_base_url": saved["oic_base_url"],
        "auth_mode": saved["auth_mode"],
        "polling_seconds": int(saved["polling_seconds"]),
        "notification_email": saved["notification_email"],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/audit-logs", response_model=list[AuditLogEntry])
def audit_logs(
    authorization: str | None = Header(default=None),
    limit: int = Query(default=50, ge=1, le=300),
) -> list[AuditLogEntry]:
    _require_actor_email(authorization)
    rows = repository.get_audit_logs(limit=limit)
    return [AuditLogEntry(**row) for row in rows]


@app.post("/api/mock-collector/run")
def run_mock_collector(authorization: str | None = Header(default=None)) -> dict[str, int]:
    actor = _optional_actor_email(authorization) or "anonymous"
    updated = collector.collect_cycle()
    repository.log_audit(
        actor_email=actor,
        action_type="manual_collector_trigger",
        target="mock_collector",
        details=f"Manual collector run updated {updated} integrations",
    )
    return {"updated_integrations": updated}
