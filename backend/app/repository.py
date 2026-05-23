from __future__ import annotations

"""Compatibility repository shim.

This module preserves the historical ``OICRepository`` import path while delegating
to domain-specific repositories. Business logic now lives in:
  - app.repositories.integrations_repository
  - app.repositories.alerts_repository
  - app.repositories.trends_repository
  - app.repositories.latency_repository
  - app.repositories.collector_repository
"""

from app.repositories.alerts_repository import AlertsRepository
from app.repositories.collector_repository import CollectorRepository
from app.repositories.integrations_repository import IntegrationsRepository
from app.repositories.latency_repository import LatencyRepository
from app.repositories.trends_repository import TrendsRepository


class OICRepository:
    def __init__(self) -> None:
        self.integrations = IntegrationsRepository()
        self.alerts = AlertsRepository()
        self.trends = TrendsRepository()
        self.latency = LatencyRepository()
        self.collector = CollectorRepository()

    def seed_if_empty(self, total: int = 170) -> None:
        self.integrations.seed_if_empty(total=total)

    def list_integrations(self, **kwargs):
        return self.integrations.list_integrations(**kwargs)

    def get_filter_options(self):
        return self.integrations.get_filter_options()

    def get_integration_detail(self, integration_id: str):
        return self.integrations.get_integration_detail(integration_id)

    def get_executive_summary(self):
        return self.integrations.get_executive_summary()

    def get_alerts(self, *, limit: int, include_acknowledged: bool):
        return self.alerts.get_alerts(limit=limit, include_acknowledged=include_acknowledged)

    def acknowledge_alert(self, alert_id: int) -> bool:
        return self.alerts.acknowledge_alert(alert_id)

    def get_trend_snapshots(self, days: int):
        return self.trends.get_trend_snapshots(days=days)

    def log_latency(self, *, endpoint: str, method: str, latency_ms: float) -> None:
        self.latency.log_latency(endpoint=endpoint, method=method, latency_ms=latency_ms)

    def get_latency_logs(self, *, endpoint: str | None, limit: int):
        return self.latency.get_latency_logs(endpoint=endpoint, limit=limit)

    def collect_mock_cycle(self) -> int:
        return self.collector.collect_mock_cycle()
