from __future__ import annotations

from app.repository import OICRepository


class AlertsRepository:
    def __init__(self, legacy_repository: OICRepository) -> None:
        self.legacy = legacy_repository

    def get_alerts(self, *, limit: int, include_acknowledged: bool):
        return self.legacy.get_alerts(limit=limit, include_acknowledged=include_acknowledged)

    def acknowledge_alert(self, alert_id: int) -> bool:
        return self.legacy.acknowledge_alert(alert_id)
