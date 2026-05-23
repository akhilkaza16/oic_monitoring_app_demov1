from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from app.database import get_connection
from app.models import IntegrationSummary, RunEvent, SettingsPayload
from app.services.mock_data import build_seed_dataset


class OICRepository:
    def seed_if_empty(self, total: int = 170) -> None:
        with get_connection() as connection:
            count = connection.execute("SELECT COUNT(*) FROM integrations").fetchone()[0]
            if count > 0:
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
            connection.commit()

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

        if total == 0:
            score = 0.0
        else:
            weighted = healthy * 1.0 + warning * 0.6 + critical * 0.2 + unknown * 0.4
            score = round((weighted / total) * 100, 2)

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

    def log_latency(self, *, endpoint: str, method: str, latency_ms: float) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with get_connection() as connection:
            connection.execute(
                "INSERT INTO latency_logs (endpoint, method, latency_ms, created_at) VALUES (?, ?, ?, ?)",
                (endpoint, method, round(latency_ms, 2), now),
            )
            connection.commit()

    def get_latency_logs(self, *, endpoint: str | None, limit: int) -> list[dict]:
        query = "SELECT endpoint, method, latency_ms, created_at FROM latency_logs"
        params: list[str | int] = []
        if endpoint:
            query += " WHERE endpoint LIKE ?"
            params.append(f"%{endpoint}%")
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        with get_connection() as connection:
            rows = connection.execute(query, params).fetchall()

        return [
            {
                "endpoint": row["endpoint"],
                "method": row["method"],
                "latency_ms": row["latency_ms"],
                "created_at": datetime.fromisoformat(row["created_at"]),
            }
            for row in rows
        ]

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
        }
        with get_connection() as connection:
            connection.executemany(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                [(key, value) for key, value in values.items()],
            )
            connection.commit()
        return values

    def collect_mock_cycle(self) -> int:
        now = datetime.now(timezone.utc)
        rng = random.Random(int(now.timestamp()))

        with get_connection() as connection:
            rows = connection.execute(
                "SELECT integration_id, status, failed_instances, connection_errors, timeouts, aborted_runs, scheduled_runs_missed FROM integrations"
            ).fetchall()

            if not rows:
                return 0

            sample_size = max(25, int(len(rows) * 0.2))
            target_rows = rng.sample(list(rows), k=min(sample_size, len(rows)))

            updated = 0
            for row in target_rows:
                current_status = row["status"]
                next_status = rng.choices(
                    ["healthy", "warning", "critical", "unknown"],
                    weights=self._transition_weights(current_status),
                    k=1,
                )[0]

                failed = max(0, row["failed_instances"] + rng.randint(-2, 3))
                conn_errors = max(0, row["connection_errors"] + rng.randint(-1, 2))
                timeouts = max(0, row["timeouts"] + rng.randint(-1, 3))
                aborted = max(0, row["aborted_runs"] + rng.randint(-1, 1))
                missed = max(0, row["scheduled_runs_missed"] + rng.randint(-1, 1))

                if next_status == "healthy":
                    failed = max(0, failed - 2)
                    conn_errors = max(0, conn_errors - 1)
                    timeouts = max(0, timeouts - 1)
                elif next_status == "critical":
                    failed += rng.randint(1, 5)
                    conn_errors += rng.randint(0, 3)
                    timeouts += rng.randint(0, 4)

                penalty = failed * 1.5 + conn_errors * 2 + timeouts * 1.2 + aborted + missed
                success_rate = max(55.0, min(99.8, 99.9 - penalty))

                connection.execute(
                    """
                    UPDATE integrations
                    SET status = ?, failed_instances = ?, connection_errors = ?,
                        timeouts = ?, aborted_runs = ?, scheduled_runs_missed = ?,
                        success_rate = ?, last_run_at = ?
                    WHERE integration_id = ?
                    """,
                    (
                        next_status,
                        failed,
                        conn_errors,
                        timeouts,
                        aborted,
                        missed,
                        round(success_rate, 2),
                        now.isoformat(),
                        row["integration_id"],
                    ),
                )

                error_type = None
                message = "Completed successfully"
                if next_status != "healthy":
                    choices = ["ConnectionError", "Timeout", "RuntimeAbort", "MappingError"]
                    error_type = rng.choice(choices)
                    message = f"{error_type} generated during mock collector cycle"

                connection.execute(
                    """
                    INSERT INTO run_events (integration_id, event_time, run_status, duration_ms, error_type, message)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row["integration_id"],
                        now.isoformat(),
                        next_status,
                        rng.randint(220, 6000),
                        error_type,
                        message,
                    ),
                )
                updated += 1

            cutoff = (now - timedelta(days=3)).isoformat()
            connection.execute("DELETE FROM run_events WHERE event_time < ?", (cutoff,))
            connection.commit()

        return updated

    @staticmethod
    def _transition_weights(current_status: str) -> list[float]:
        if current_status == "healthy":
            return [0.75, 0.18, 0.04, 0.03]
        if current_status == "warning":
            return [0.28, 0.48, 0.18, 0.06]
        if current_status == "critical":
            return [0.18, 0.34, 0.40, 0.08]
        return [0.30, 0.25, 0.25, 0.20]
