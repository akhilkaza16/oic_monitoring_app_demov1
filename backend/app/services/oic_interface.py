from __future__ import annotations

from abc import ABC, abstractmethod

from app.repositories.collector_repository import CollectorRepository


class OICCollectorInterface(ABC):
    @abstractmethod
    def collect_cycle(self) -> int:
        """Runs one collection cycle and returns updated integration count."""


class MockOICCollector(OICCollectorInterface):
    def __init__(self, repository: CollectorRepository) -> None:
        self.repository = repository

    def collect_cycle(self) -> int:
        return self.repository.collect_mock_cycle()
