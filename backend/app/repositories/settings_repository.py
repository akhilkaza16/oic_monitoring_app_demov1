from __future__ import annotations

from datetime import datetime, timezone

from app.database import get_connection
from app.models import SettingsPayload


class SettingsRepository:
    def get_settings(self) -> dict[str, str]:
        with get_connection() as connection:
            rows = connection.execute("SELECT key, value FROM settings ORDER BY key").fetchall()
        return {row["key"]: row["value"] for row in rows}

    def upsert_settings(self, payload: SettingsPayload) -> dict[str, str]:
        values = {
            "oic_base_url": payload.oic_base_url,
            "auth_mode": payload.auth_mode,
            "polling_seconds": str(payload.polling_seconds),
            "notification_email": payload.notification_email,
            "threshold_issue_score_warning": str(payload.threshold_issue_score_warning),
            "threshold_issue_score_critical": str(payload.threshold_issue_score_critical),
            "threshold_missed_schedules_warning": str(payload.threshold_missed_schedules_warning),
            "threshold_missed_schedules_critical": str(payload.threshold_missed_schedules_critical),
            "threshold_critical_integrations_warning": str(payload.threshold_critical_integrations_warning),
            "threshold_critical_integrations_critical": str(payload.threshold_critical_integrations_critical),
            "webhook_enabled": "true" if payload.webhook_enabled else "false",
            "webhook_url": payload.webhook_url,
            "webhook_bearer_token": payload.webhook_bearer_token,
        }
        with get_connection() as connection:
            connection.executemany(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                [(key, value) for key, value in values.items()],
            )
            connection.commit()
        return values

    def log_audit(self, *, actor_email: str | None, action_type: str, target: str, details: str) -> None:
        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO audit_logs (actor_email, action_type, target, details, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    actor_email,
                    action_type,
                    target,
                    details,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            connection.commit()

    def get_audit_logs(self, *, limit: int) -> list[dict]:
        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT id, actor_email, action_type, target, details, created_at
                FROM audit_logs
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "actor_email": row["actor_email"],
                "action_type": row["action_type"],
                "target": row["target"],
                "details": row["details"],
                "created_at": datetime.fromisoformat(row["created_at"]),
            }
            for row in rows
        ]
