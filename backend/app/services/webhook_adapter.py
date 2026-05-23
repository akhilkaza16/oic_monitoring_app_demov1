from __future__ import annotations

import time
from datetime import datetime, timezone

import requests

from app.database import get_connection
from app.repositories.settings_repository import SettingsRepository


class WebhookAdapter:
    def __init__(self, settings_repository: SettingsRepository) -> None:
        self.settings_repository = settings_repository

    def send_alert_event(
        self,
        *,
        severity: str,
        integration_id: str,
        alert_title: str,
        event_time_iso: str,
    ) -> None:
        settings = self.settings_repository.get_settings()
        webhook_enabled = settings.get("webhook_enabled", "false").lower() == "true"
        webhook_url = settings.get("webhook_url", "").strip()
        webhook_token = settings.get("webhook_bearer_token", "").strip()

        if not webhook_enabled or not webhook_url:
            return

        payload = {
            "event": "oic_alert",
            "severity": severity,
            "timestamp": event_time_iso,
            "integration_id": integration_id,
            "title": alert_title,
        }
        headers = {"Content-Type": "application/json"}
        if webhook_token:
            headers["Authorization"] = f"Bearer {webhook_token}"

        attempts = 0
        last_status = None
        last_error = None

        for attempt in range(1, 4):
            attempts = attempt
            try:
                response = requests.post(webhook_url, json=payload, headers=headers, timeout=3)
                last_status = response.status_code
                if 200 <= response.status_code < 300:
                    self._log_delivery(
                        event_type="oic_alert",
                        severity=severity,
                        status="success",
                        attempts=attempts,
                        http_status=last_status,
                        error_message=None,
                    )
                    return
                last_error = f"Non-success status {response.status_code}"
            except requests.RequestException as exc:
                last_error = str(exc)

            if attempt < 3:
                time.sleep(0.5 * (2 ** (attempt - 1)))

        self._log_delivery(
            event_type="oic_alert",
            severity=severity,
            status="failed",
            attempts=attempts,
            http_status=last_status,
            error_message=last_error,
        )

    def _log_delivery(
        self,
        *,
        event_type: str,
        severity: str,
        status: str,
        attempts: int,
        http_status: int | None,
        error_message: str | None,
    ) -> None:
        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO webhook_delivery_logs (
                  event_type, severity, status, attempts, http_status, error_message, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_type,
                    severity,
                    status,
                    attempts,
                    http_status,
                    error_message,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            connection.commit()
