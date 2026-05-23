from __future__ import annotations

from app.repository import OICRepository


class CollectorRepository:
    def __init__(self, legacy_repository: OICRepository) -> None:
        self.legacy = legacy_repository

    def collect_mock_cycle(self) -> int:
        return self.legacy.collect_mock_cycle()
