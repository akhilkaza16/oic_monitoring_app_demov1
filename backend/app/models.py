from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

StatusType = Literal["healthy", "warning", "critical", "unknown"]
AlertSeverity = Literal["critical", "warning", "info"]


class IntegrationSummary(BaseModel):
    integration_id: str
    name: str
    project: str
    business_domain: str
    owner: str
    status: StatusType
    failed_instances: int
    connection_errors: int
    timeouts: int
    aborted_runs: int
    scheduled_runs_missed: int
    success_rate: float
    last_run_at: datetime


class Recommendation(BaseModel):
    priority: int
    title: str
    rationale: str
    action: str


class RunEvent(BaseModel):
    event_time: datetime
    run_status: StatusType
    duration_ms: int
    error_type: str | None
    message: str


class IntegrationDetailResponse(BaseModel):
    integration: IntegrationSummary
    endpoint_url: str
    recommendations: list[Recommendation]
    recent_runs: list[RunEvent]


class IntegrationListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[IntegrationSummary]


class ExecutiveSummaryResponse(BaseModel):
    health_score: float = Field(..., ge=0, le=100)
    total_integrations: int
    healthy_count: int
    warning_count: int
    critical_count: int
    unknown_count: int
    critical_incidents: int
    top_failing_integrations: list[IntegrationSummary]
    last_refresh: datetime


class LatencyLog(BaseModel):
    endpoint: str
    method: str
    latency_ms: float
    created_at: datetime


class SettingsPayload(BaseModel):
    oic_base_url: str
    auth_mode: str
    polling_seconds: int = Field(..., ge=10, le=600)
    notification_email: str
    threshold_issue_score_warning: int = Field(..., ge=1, le=200)
    threshold_issue_score_critical: int = Field(..., ge=1, le=250)
    threshold_missed_schedules_warning: int = Field(..., ge=1, le=30)
    threshold_missed_schedules_critical: int = Field(..., ge=1, le=60)
    threshold_critical_integrations_warning: int = Field(..., ge=1, le=170)
    threshold_critical_integrations_critical: int = Field(..., ge=1, le=170)
    webhook_enabled: bool
    webhook_url: str
    webhook_bearer_token: str
    webhook_max_retries: int = Field(..., ge=1, le=3)
    webhook_initial_backoff_seconds: float = Field(..., ge=0.5, le=2.0)
    webhook_timeout_seconds: int = Field(..., ge=2, le=6)


class AuthPayload(BaseModel):
    email: str
    password: str = Field(..., min_length=8, max_length=128)


class AuthStatusResponse(BaseModel):
    has_admin: bool
    authenticated_email: str | None


class AuthResponse(BaseModel):
    token: str
    email: str


class PasswordResetRequestPayload(BaseModel):
    email: str


class PasswordResetRequestResponse(BaseModel):
    status: str
    reset_code: str
    expires_in_minutes: int


class PasswordResetConfirmPayload(BaseModel):
    email: str
    reset_code: str
    new_password: str = Field(..., min_length=10, max_length=128)


class AuditLogEntry(BaseModel):
    id: int
    actor_email: str | None
    action_type: str
    target: str
    details: str
    created_at: datetime


class TrendSnapshot(BaseModel):
    snapshot_date: str
    healthy_count: int
    warning_count: int
    critical_count: int
    unknown_count: int
    health_score: float


class AlertEvent(BaseModel):
    id: int
    severity: AlertSeverity
    integration_id: str
    title: str
    message: str
    simulated_email_to: str
    created_at: datetime
    acknowledged: bool
    metric_type: str | None = None
    metric_value: int | None = None
