from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

StatusType = Literal["healthy", "warning", "critical", "unknown"]


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
