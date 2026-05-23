from __future__ import annotations

from app.repository import OICRepository


class TrendsRepository:
    def __init__(self, legacy_repository: OICRepository) -> None:
        self.legacy = legacy_repository

    def get_trend_snapshots(self, days: int):
        return self.legacy.get_trend_snapshots(days=days)
