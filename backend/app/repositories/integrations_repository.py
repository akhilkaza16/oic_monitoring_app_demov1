from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from app.database import get_connection
from app.models import IntegrationSummary, RunEvent
from app.services.mock_data import build_seed_dataset


def _compute_health_score(*, healthy: int, warning: int, critical: int, unknown: int) -> float:
    total = healthy + warning + critical + unknown
    if total == 0:
        return 0.0
    weighted = healthy * 1.0 + warning * 0.6 + critical * 0.2 + unknown * 0.4
    return round((weighted / total) * 100, 2)


class IntegrationsRepository:
    def seed_if_empty(self, total: int = 170) -> None:
        with get_connection() as connection:
            count = connection.execute("SELECT COUNT(*) FROM integrations").fetchone()[0]
            if count > 0:
                self._ensure_default_settings(connection)
                trend_count = connection.execute("SELECT COUNT(*) FROM trend_snapshots").fetchone()[0]
                alert_count = connection.execute("SELECT COUNT(*) FROM alert_events").fetchone()[0]
                if trend_count < 30:
                    self._seed_trend_history(connection)
                if alert_count == 0:
                    self._seed_initial_alerts(connection)
                connection.commit()
                self.record_daily_snapshot(connection)
                return

            integrations, run_events, settings = build_seed_dataset(total)
            connection.executemany(
                """
                INSERT INTO integrations (
                  integration_id, name, project, business_domain, owner, endpoint_url, status,
                  failed_instances, connection_errors, timeouts, aborted_runs,
                  scheduled_runs_missed, success_rate, last_run_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        item["integration_id"],
                        item["name"],
                        item["project"],
                        item["business_domain"],
                        item["owner"],
                        item["endpoint_url"],
                        item["status"],
                        item["failed_instances"],
                        item["connection_errors"],
                        item["timeouts"],
                        item["aborted_runs"],
                        item["scheduled_runs_missed"],
                        item["success_rate"],
                        item["last_run_at"],
                    )
                    for item in integrations
                ],
            )
            connection.executemany(
                """
                INSERT INTO run_events (integration_id, event_time, run_status, duration_ms, error_type, message)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        event["integration_id"],
                        event["event_time"],
                        event["run_status"],
                        event["duration_ms"],
                        event["error_type"],
                        event["message"],
                    )
                    for event in run_events
                ],
            )
            connection.executemany(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                [(key, value) for key, value in settings.items()],
            )
            self._seed_trend_history(connection)
            self._seed_initial_alerts(connection)
            connection.commit()

    def list_integrations(
        self,
        *,
        status: str | None,
        project: str | None,
        business_domain: str | None,
        search: str | None,
        limit: int,
        offset: int,
    ) -> tuple[int, list[IntegrationSummary]]:
        where = ["1=1"]
        params: list[str | int] = []

        if status:
            where.append("status = ?")
            params.append(status)
        if project:
            where.append("project = ?")
            params.append(project)
        if business_domain:
            where.append("business_domain = ?")
            params.append(business_domain)
        if search:
            where.append("(name LIKE ? OR integration_id LIKE ?)")
            params.extend([f"%{search}%", f"%{search}%"])

        where_sql = " AND ".join(where)

        with get_connection() as connection:
            total = connection.execute(
                f"SELECT COUNT(*) FROM integrations WHERE {where_sql}",
                params,
            ).fetchone()[0]
            rows = connection.execute(
                f"""
                SELECT *
                FROM integrations
                WHERE {where_sql}
                ORDER BY
                  CASE status
                    WHEN 'critical' THEN 1
                    WHEN 'warning' THEN 2
                    WHEN 'unknown' THEN 3
                    ELSE 4
                  END,
                  failed_instances DESC,
                  name ASC
                LIMIT ? OFFSET ?
                """,
                [*params, limit, offset],
            ).fetchall()

        return total, [self._row_to_summary(row) for row in rows]

    def get_filter_options(self) -> dict[str, list[str]]:
        with get_connection() as connection:
            projects = [row[0] for row in connection.execute("SELECT DISTINCT project FROM integrations ORDER BY project")]
            domains = [
                row[0]
                for row in connection.execute(
                    "SELECT DISTINCT business_domain FROM integrations ORDER BY business_domain"
                )
            ]
        return {"projects": projects, "business_domains": domains}

    def get_integration_detail(self, integration_id: str) -> tuple[IntegrationSummary, str, list[RunEvent]] | None:
        with get_connection() as connection:
            integration_row = connection.execute(
                "SELECT * FROM integrations WHERE integration_id = ?",
                (integration_id,),
            ).fetchone()
            if integration_row is None:
                return None

            run_rows = connection.execute(
                """
                SELECT event_time, run_status, duration_ms, error_type, message
                FROM run_events
                WHERE integration_id = ?
                ORDER BY event_time DESC
                LIMIT 20
                """,
                (integration_id,),
            ).fetchall()

        summary = self._row_to_summary(integration_row)
        runs = [
            RunEvent(
                event_time=datetime.fromisoformat(row["event_time"]),
                run_status=row["run_status"],
                duration_ms=row["duration_ms"],
                error_type=row["error_type"],
                message=row["message"],
            )
            for row in run_rows
        ]
        return summary, integration_row["endpoint_url"], runs

    def get_executive_summary(self) -> dict:
        with get_connection() as connection:
            total = connection.execute("SELECT COUNT(*) FROM integrations").fetchone()[0]
            grouped_rows = connection.execute(
                "SELECT status, COUNT(*) AS count FROM integrations GROUP BY status"
            ).fetchall()
            latest = connection.execute("SELECT MAX(last_run_at) FROM integrations").fetchone()[0]
            top_failing_rows = connection.execute(
                """
                SELECT *
                FROM integrations
                ORDER BY (failed_instances + connection_errors + timeouts + aborted_runs + scheduled_runs_missed) DESC,
                         success_rate ASC
                LIMIT 5
                """
            ).fetchall()

        grouped = {row["status"]: row["count"] for row in grouped_rows}
        healthy = grouped.get("healthy", 0)
        warning = grouped.get("warning", 0)
        critical = grouped.get("critical", 0)
        unknown = grouped.get("unknown", 0)

        score = _compute_health_score(healthy=healthy, warning=warning, critical=critical, unknown=unknown)

        critical_incidents = sum(
            item.failed_instances + item.connection_errors + item.timeouts + item.aborted_runs
            for item in [self._row_to_summary(row) for row in top_failing_rows]
        )

        return {
            "health_score": score,
            "total_integrations": total,
            "healthy_count": healthy,
            "warning_count": warning,
            "critical_count": critical,
            "unknown_count": unknown,
            "critical_incidents": critical_incidents,
            "top_failing_integrations": [self._row_to_summary(row) for row in top_failing_rows],
            "last_refresh": datetime.fromisoformat(latest) if latest else datetime.now(timezone.utc),
        }

    def record_daily_snapshot(self, connection=None) -> None:
        own_connection = connection is None
        conn = connection or get_connection()
        try:
            today = datetime.now(timezone.utc).date().isoformat()
            healthy, warning, critical, unknown = self._status_counts(conn)
            score = _compute_health_score(
                healthy=healthy,
                warning=warning,
                critical=critical,
                unknown=unknown,
            )
            conn.execute(
                """
                INSERT OR REPLACE INTO trend_snapshots (
                  snapshot_date, healthy_count, warning_count, critical_count,
                  unknown_count, health_score, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (today, healthy, warning, critical, unknown, score, datetime.now(timezone.utc).isoformat()),
            )
            if own_connection:
                conn.commit()
        finally:
            if own_connection:
                conn.close()

    def _row_to_summary(self, row) -> IntegrationSummary:
        return IntegrationSummary(
            integration_id=row["integration_id"],
            name=row["name"],
            project=row["project"],
            business_domain=row["business_domain"],
            owner=row["owner"],
            status=row["status"],
            failed_instances=row["failed_instances"],
            connection_errors=row["connection_errors"],
            timeouts=row["timeouts"],
            aborted_runs=row["aborted_runs"],
            scheduled_runs_missed=row["scheduled_runs_missed"],
            success_rate=row["success_rate"],
            last_run_at=datetime.fromisoformat(row["last_run_at"]),
        )

    def _status_counts(self, connection) -> tuple[int, int, int, int]:
        grouped_rows = connection.execute(
            "SELECT status, COUNT(*) AS count FROM integrations GROUP BY status"
        ).fetchall()
        grouped = {row["status"]: row["count"] for row in grouped_rows}
        return (
            grouped.get("healthy", 0),
            grouped.get("warning", 0),
            grouped.get("critical", 0),
            grouped.get("unknown", 0),
        )

    def _seed_trend_history(self, connection) -> None:
        healthy, warning, critical, unknown = self._status_counts(connection)
        rng = random.Random(30)
        total = healthy + warning + critical + unknown
        today = datetime.now(timezone.utc).date()

        for days_ago in range(29, -1, -1):
            day = today - timedelta(days=days_ago)
            drift = max(1, int((days_ago / 30) * 6))
            day_critical = max(5, min(total // 3, critical + rng.randint(-drift, drift)))
            day_warning = max(10, min(total // 2, warning + rng.randint(-drift * 2, drift * 2)))
            day_unknown = max(3, min(total // 5, unknown + rng.randint(-2, 2)))
            day_healthy = max(0, total - day_critical - day_warning - day_unknown)

            score = _compute_health_score(
                healthy=day_healthy,
                warning=day_warning,
                critical=day_critical,
                unknown=day_unknown,
            )
            connection.execute(
                """
                INSERT OR REPLACE INTO trend_snapshots (
                  snapshot_date, healthy_count, warning_count, critical_count,
                  unknown_count, health_score, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    day.isoformat(),
                    day_healthy,
                    day_warning,
                    day_critical,
                    day_unknown,
                    score,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    def _seed_initial_alerts(self, connection) -> None:
        settings = {
            row["key"]: row["value"]
            for row in connection.execute("SELECT key, value FROM settings")
        }
        notify_to = settings.get("notification_email", "ops-team@example.com")
        rows = connection.execute(
            """
            SELECT integration_id, failed_instances, timeouts, connection_errors
            FROM integrations
            WHERE status = 'critical'
            ORDER BY (failed_instances + timeouts + connection_errors) DESC
            LIMIT 5
            """
        ).fetchall()

        now = datetime.now(timezone.utc).isoformat()
        for row in rows:
            issue_total = row["failed_instances"] + row["timeouts"] + row["connection_errors"]
            connection.execute(
                """
                INSERT INTO alert_events (
                  severity, integration_id, title, message, simulated_email_to, created_at, acknowledged,
                  metric_type, metric_value
                ) VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)
                """,
                (
                    "critical",
                    row["integration_id"],
                    "Critical integration health alert",
                    f"{row['integration_id']} currently has {issue_total} combined critical issue signals.",
                    notify_to,
                    now,
                    "issue_score",
                    issue_total,
                ),
            )

    def _ensure_default_settings(self, connection) -> None:
        required_settings_defaults = {
            "threshold_issue_score_warning": "12",
            "threshold_issue_score_critical": "18",
            "threshold_missed_schedules_warning": "3",
            "threshold_missed_schedules_critical": "5",
            "threshold_critical_integrations_warning": "20",
            "threshold_critical_integrations_critical": "35",
            "webhook_enabled": "false",
            "webhook_url": "",
            "webhook_bearer_token": "",
            "webhook_max_retries": "3",
            "webhook_initial_backoff_seconds": "0.5",
            "webhook_timeout_seconds": "3",
        }
        for key, value in required_settings_defaults.items():
            existing = connection.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
            if existing is None or str(existing[0]).strip() == "":
                connection.execute(
                    "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                    (key, value),
                )
