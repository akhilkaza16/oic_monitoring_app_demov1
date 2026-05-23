from __future__ import annotations

from datetime import datetime

from app.database import get_connection


class AlertsRepository:
    def get_alerts(self, *, limit: int, include_acknowledged: bool):
        query = """
            SELECT id, severity, integration_id, title, message, simulated_email_to, created_at, acknowledged,
                   metric_type, metric_value
            FROM alert_events
        """
        params: list[int] = []
        if not include_acknowledged:
            query += " WHERE acknowledged = 0"
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        with get_connection() as connection:
            settings = {row["key"]: row["value"] for row in connection.execute("SELECT key, value FROM settings")}
            rows = connection.execute(query, params).fetchall()

        issue_warning = int(settings.get("threshold_issue_score_warning", "12"))
        missed_warning = int(settings.get("threshold_missed_schedules_warning", "3"))
        critical_count_warning = int(settings.get("threshold_critical_integrations_warning", "20"))

        filtered: list[dict] = []
        for row in rows:
            metric_type = row["metric_type"]
            metric_value = row["metric_value"]

            if metric_type == "issue_score" and metric_value is not None and metric_value < issue_warning:
                continue
            if metric_type == "missed_schedules" and metric_value is not None and metric_value < missed_warning:
                continue
            if (
                metric_type == "critical_integrations_count"
                and metric_value is not None
                and metric_value < critical_count_warning
            ):
                continue

            filtered.append(
                {
                    "id": row["id"],
                    "severity": row["severity"],
                    "integration_id": row["integration_id"],
                    "title": row["title"],
                    "message": row["message"],
                    "simulated_email_to": row["simulated_email_to"],
                    "created_at": datetime.fromisoformat(row["created_at"]),
                    "acknowledged": bool(row["acknowledged"]),
                    "metric_type": metric_type,
                    "metric_value": metric_value,
                }
            )

        return filtered

    def acknowledge_alert(self, alert_id: int) -> bool:
        with get_connection() as connection:
            cursor = connection.execute(
                "UPDATE alert_events SET acknowledged = 1 WHERE id = ?",
                (alert_id,),
            )
            connection.commit()
        return cursor.rowcount > 0
