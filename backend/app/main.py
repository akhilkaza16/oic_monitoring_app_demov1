from __future__ import annotations

import secrets
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Header, HTTPException, Query, Request, Response
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
    PasswordResetConfirmPayload,
    PasswordResetRequestPayload,
    PasswordResetRequestResponse,
    SettingsPayload,
    TrendSnapshot,
)
from app.repositories.alerts_repository import AlertsRepository
from app.repositories.auth_repository import AuthRepository
from app.repositories.collector_repository import CollectorRepository
from app.repositories.integrations_repository import IntegrationsRepository
from app.repositories.latency_repository import LatencyRepository
from app.repositories.settings_repository import SettingsRepository
from app.repositories.trends_repository import TrendsRepository
from app.services.auth_service import create_token, validate_token_data
from app.services.rules_engine import build_recommendations

auth_repository = AuthRepository()
settings_repository = SettingsRepository()
integrations_repository = IntegrationsRepository()
alerts_repository = AlertsRepository()
trends_repository = TrendsRepository()
latency_repository = LatencyRepository()
collector_repository = CollectorRepository()

SESSION_COOKIE_NAME = "session_token"
CSRF_COOKIE_NAME = "csrf_token"


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_database()
    integrations_repository.seed_if_empty(total=170)
    yield


app = FastAPI(title="badger-oic-monitor", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_origin_regex=r"https://.*\.preview\.emergentagent\.com",
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
        latency_repository.log_latency(
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


def _resolve_auth_token(request: Request, authorization: str | None) -> tuple[str | None, bool]:
    bearer_token = _read_bearer_token(authorization)
    if bearer_token:
        return bearer_token, True
    cookie_token = request.cookies.get(SESSION_COOKIE_NAME)
    return cookie_token, False


def _set_auth_cookies(response: Response, token: str) -> None:
    csrf_token = secrets.token_urlsafe(24)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=False,
        samesite="strict",
        path="/",
    )
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=csrf_token,
        httponly=False,
        secure=False,
        samesite="strict",
        path="/",
    )


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    response.delete_cookie(CSRF_COOKIE_NAME, path="/")


def _optional_actor_email(request: Request, authorization: str | None) -> str | None:
    token, _ = _resolve_auth_token(request, authorization)
    if not token:
        return None
    try:
        payload = validate_token_data(token)
        email = str(payload["sub"])
        session_id = str(payload.get("sid", ""))
        if session_id and not auth_repository.is_session_active(email=email, session_id=session_id):
            return None
        return email
    except ValueError:
        return None


def _require_actor_email(
    request: Request,
    authorization: str | None,
    csrf_header: str | None = None,
    enforce_csrf: bool = False,
) -> str:
    token, using_bearer = _resolve_auth_token(request, authorization)
    if not token:
        raise HTTPException(status_code=401, detail="Authorization token required")

    if enforce_csrf and not using_bearer:
        csrf_cookie = request.cookies.get(CSRF_COOKIE_NAME)
        if not csrf_cookie or not csrf_header or csrf_header != csrf_cookie:
            raise HTTPException(status_code=403, detail="CSRF validation failed")

    try:
        payload = validate_token_data(token)
        email = str(payload["sub"])
        session_id = str(payload.get("sid", ""))
        if session_id and not auth_repository.is_session_active(email=email, session_id=session_id):
            raise HTTPException(status_code=401, detail="Session revoked or expired")
        return email
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "badger-oic-monitor-backend"}


@app.get("/api/auth/status", response_model=AuthStatusResponse)
def auth_status(request: Request, authorization: str | None = Header(default=None)) -> AuthStatusResponse:
    actor = _optional_actor_email(request, authorization)
    return AuthStatusResponse(has_admin=auth_repository.has_admin_user(), authenticated_email=actor)


@app.post("/api/auth/register-admin", response_model=AuthResponse)
def register_admin(payload: AuthPayload, response: Response) -> AuthResponse:
    email = payload.email.lower().strip()
    if auth_repository.has_admin_user():
        settings_repository.log_audit(
            actor_email=email,
            action_type="admin_register_rejected",
            target="admin_users",
            details="Registration attempt rejected because admin already exists",
        )
        raise HTTPException(status_code=409, detail="Admin is already configured")

    try:
        created_email = auth_repository.create_first_admin(email=email, password=payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    session_id, _ = auth_repository.create_session(email=created_email, revoke_previous=True)
    token = create_token(created_email, session_id)
    _set_auth_cookies(response, token)

    settings_repository.log_audit(
        actor_email=created_email,
        action_type="admin_registered",
        target="admin_users",
        details="First admin account created from settings page",
    )
    return AuthResponse(token=token, email=created_email)


@app.post("/api/auth/login", response_model=AuthResponse)
def login_admin(payload: AuthPayload, response: Response) -> AuthResponse:
    is_valid, reason = auth_repository.verify_admin_credentials(email=payload.email, password=payload.password)
    email = payload.email.lower().strip()

    settings_repository.log_audit(
        actor_email=email,
        action_type="login_success" if is_valid else "login_failed",
        target="admin_users",
        details=reason,
    )
    if not is_valid:
        status_code = 423 if "locked" in reason.lower() else 401
        raise HTTPException(status_code=status_code, detail=reason)

    session_id, _ = auth_repository.create_session(email=email, revoke_previous=True)
    token = create_token(email, session_id)
    _set_auth_cookies(response, token)
    return AuthResponse(token=token, email=email)


@app.post("/api/auth/logout")
def logout_admin(request: Request, response: Response, authorization: str | None = Header(default=None)) -> dict[str, str]:
    actor = _optional_actor_email(request, authorization)
    if actor:
        auth_repository.revoke_all_sessions(email=actor, reason="logout")
        settings_repository.log_audit(
            actor_email=actor,
            action_type="logout",
            target="admin_users",
            details="Admin logout request",
        )
    _clear_auth_cookies(response)
    return {"status": "logged_out"}


@app.post("/api/auth/password-reset/request", response_model=PasswordResetRequestResponse)
def request_password_reset(payload: PasswordResetRequestPayload) -> PasswordResetRequestResponse:
    try:
        reset_code = auth_repository.create_password_reset_code(email=payload.email, expiry_minutes=60)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    settings_repository.log_audit(
        actor_email=payload.email.lower().strip(),
        action_type="password_reset_requested",
        target="admin_users",
        details="One-time reset code generated",
    )
    return PasswordResetRequestResponse(status="code_generated", reset_code=reset_code, expires_in_minutes=60)


@app.post("/api/auth/password-reset/confirm")
def confirm_password_reset(payload: PasswordResetConfirmPayload) -> dict[str, str]:
    success, message = auth_repository.reset_password_with_code(
        email=payload.email,
        reset_code=payload.reset_code,
        new_password=payload.new_password,
    )
    if not success:
        raise HTTPException(status_code=400, detail=message)

    settings_repository.log_audit(
        actor_email=payload.email.lower().strip(),
        action_type="password_reset_completed",
        target="admin_users",
        details="Password reset completed and sessions revoked",
    )
    return {"status": "password_reset_completed"}


@app.post("/api/security/revoke-sessions")
def revoke_sessions(
    request: Request,
    response: Response,
    authorization: str | None = Header(default=None),
    x_csrf_token: str | None = Header(default=None),
) -> dict[str, int]:
    actor = _require_actor_email(
        request,
        authorization,
        csrf_header=x_csrf_token,
        enforce_csrf=True,
    )
    revoked = auth_repository.revoke_all_sessions(email=actor, reason="manual_revoke_all")
    _clear_auth_cookies(response)
    settings_repository.log_audit(
        actor_email=actor,
        action_type="sessions_revoked",
        target="admin_sessions",
        details=f"Revoked {revoked} active sessions",
    )
    return {"revoked_sessions": revoked}


@app.get("/api/executive-summary", response_model=ExecutiveSummaryResponse)
def executive_summary() -> ExecutiveSummaryResponse:
    summary = integrations_repository.get_executive_summary()
    return ExecutiveSummaryResponse(**summary)


@app.get("/api/trends", response_model=list[TrendSnapshot])
def trend_snapshots(days: int = Query(default=30, ge=7, le=90)) -> list[TrendSnapshot]:
    rows = trends_repository.get_trend_snapshots(days=days)
    return [TrendSnapshot(**row) for row in rows]


@app.get("/api/alerts", response_model=list[AlertEvent])
def alerts(
    limit: int = Query(default=20, ge=1, le=200),
    include_acknowledged: bool = Query(default=False),
) -> list[AlertEvent]:
    rows = alerts_repository.get_alerts(limit=limit, include_acknowledged=include_acknowledged)
    return [AlertEvent(**row) for row in rows]


@app.post("/api/alerts/{alert_id}/acknowledge")
def acknowledge_alert(
    alert_id: int,
    request: Request,
    authorization: str | None = Header(default=None),
    x_csrf_token: str | None = Header(default=None),
) -> dict[str, str]:
    actor = _require_actor_email(
        request,
        authorization,
        csrf_header=x_csrf_token,
        enforce_csrf=True,
    )
    updated = alerts_repository.acknowledge_alert(alert_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Alert not found")
    settings_repository.log_audit(
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
    total, items = integrations_repository.list_integrations(
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
    return integrations_repository.get_filter_options()


@app.get("/api/integrations/{integration_id}", response_model=IntegrationDetailResponse)
def integration_detail(integration_id: str) -> IntegrationDetailResponse:
    detail = integrations_repository.get_integration_detail(integration_id)
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
    rows = latency_repository.get_latency_logs(endpoint=endpoint, limit=limit)
    return [LatencyLog(**row) for row in rows]


@app.get("/api/settings")
def get_settings(request: Request, authorization: str | None = Header(default=None)) -> dict[str, str | int]:
    _require_actor_email(request, authorization)
    values = settings_repository.get_settings()
    return {
        "oic_base_url": values.get("oic_base_url", ""),
        "auth_mode": values.get("auth_mode", "OAuth2"),
        "polling_seconds": int(values.get("polling_seconds", "30")),
        "notification_email": values.get("notification_email", ""),
        "threshold_issue_score_warning": int(values.get("threshold_issue_score_warning", "12")),
        "threshold_issue_score_critical": int(values.get("threshold_issue_score_critical", "18")),
        "threshold_missed_schedules_warning": int(values.get("threshold_missed_schedules_warning", "3")),
        "threshold_missed_schedules_critical": int(values.get("threshold_missed_schedules_critical", "5")),
        "threshold_critical_integrations_warning": int(
            values.get("threshold_critical_integrations_warning", "20")
        ),
        "threshold_critical_integrations_critical": int(
            values.get("threshold_critical_integrations_critical", "35")
        ),
    }


@app.put("/api/settings")
def put_settings(
    payload: SettingsPayload,
    request: Request,
    authorization: str | None = Header(default=None),
    x_csrf_token: str | None = Header(default=None),
) -> dict[str, str | int]:
    actor = _require_actor_email(
        request,
        authorization,
        csrf_header=x_csrf_token,
        enforce_csrf=True,
    )

    if payload.threshold_issue_score_warning > payload.threshold_issue_score_critical:
        raise HTTPException(status_code=400, detail="Issue score warning threshold must be <= critical threshold")
    if payload.threshold_missed_schedules_warning > payload.threshold_missed_schedules_critical:
        raise HTTPException(
            status_code=400,
            detail="Missed schedules warning threshold must be <= critical threshold",
        )
    if payload.threshold_critical_integrations_warning > payload.threshold_critical_integrations_critical:
        raise HTTPException(
            status_code=400,
            detail="Critical integration count warning threshold must be <= critical threshold",
        )

    saved = settings_repository.upsert_settings(payload)
    settings_repository.log_audit(
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
        "threshold_issue_score_warning": int(saved["threshold_issue_score_warning"]),
        "threshold_issue_score_critical": int(saved["threshold_issue_score_critical"]),
        "threshold_missed_schedules_warning": int(saved["threshold_missed_schedules_warning"]),
        "threshold_missed_schedules_critical": int(saved["threshold_missed_schedules_critical"]),
        "threshold_critical_integrations_warning": int(saved["threshold_critical_integrations_warning"]),
        "threshold_critical_integrations_critical": int(saved["threshold_critical_integrations_critical"]),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/audit-logs", response_model=list[AuditLogEntry])
def audit_logs(
    request: Request,
    authorization: str | None = Header(default=None),
    limit: int = Query(default=50, ge=1, le=300),
) -> list[AuditLogEntry]:
    _require_actor_email(request, authorization)
    rows = settings_repository.get_audit_logs(limit=limit)
    return [AuditLogEntry(**row) for row in rows]


@app.post("/api/mock-collector/run")
def run_mock_collector(
    request: Request,
    authorization: str | None = Header(default=None),
    x_csrf_token: str | None = Header(default=None),
) -> dict[str, int]:
    actor = _require_actor_email(
        request,
        authorization,
        csrf_header=x_csrf_token,
        enforce_csrf=True,
    )
    updated = collector_repository.collect_mock_cycle()
    settings_repository.log_audit(
        actor_email=actor,
        action_type="manual_collector_trigger",
        target="mock_collector",
        details=f"Manual collector run updated {updated} integrations",
    )
    return {"updated_integrations": updated}
