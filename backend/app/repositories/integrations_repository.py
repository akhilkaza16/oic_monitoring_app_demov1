from __future__ import annotations

from app.repository import OICRepository


class IntegrationsRepository:
    def __init__(self, legacy_repository: OICRepository) -> None:
        self.legacy = legacy_repository

    def seed_if_empty(self, total: int = 170) -> None:
        self.legacy.seed_if_empty(total=total)

    def list_integrations(self, **kwargs):
        return self.legacy.list_integrations(**kwargs)

    def get_filter_options(self):
        return self.legacy.get_filter_options()

    def get_integration_detail(self, integration_id: str):
        return self.legacy.get_integration_detail(integration_id)

    def get_executive_summary(self):
        return self.legacy.get_executive_summary()
