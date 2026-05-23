from __future__ import annotations

from app.repository import OICRepository


class LatencyRepository:
    def __init__(self, legacy_repository: OICRepository) -> None:
        self.legacy = legacy_repository

    def log_latency(self, *, endpoint: str, method: str, latency_ms: float) -> None:
        self.legacy.log_latency(endpoint=endpoint, method=method, latency_ms=latency_ms)

    def get_latency_logs(self, *, endpoint: str | None, limit: int):
        return self.legacy.get_latency_logs(endpoint=endpoint, limit=limit)
