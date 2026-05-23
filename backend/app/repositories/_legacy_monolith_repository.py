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


class OICRepository:
    def seed_if_empty(self, total: int = 170) -> None:
        with get_connection() as connection:
            count = connection.execute("SELECT COUNT(*) FROM integrations").fetchone()[0]
            if count > 0:
                trend_count = connection.execute("SELECT COUNT(*) FROM trend_snapshots").fetchone()[0]
                alert_count = connection.execute("SELECT COUNT(*) FROM alert_events").fetchone()[0]
                required_settings_defaults = {
                    "threshold_issue_score_warning": "12",
                    "threshold_issue_score_critical": "18",
                    "threshold_missed_schedules_warning": "3",
                    "threshold_missed_schedules_critical": "5",
                    "threshold_critical_integrations_warning": "20",
                    "threshold_critical_integrations_critical": "35",
                }
                for key, value in required_settings_defaults.items():
                    connection.execute(
                        "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                        (key, value),
                    )
                if trend_count < 30:
                    self._seed_trend_history(connection)
                if alert_count == 0:
                    self._seed_initial_alerts(connection)
                connection.commit()
                self.record_daily_snapshot()
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

    def record_daily_snapshot(self) -> None:
        today = datetime.now(timezone.utc).date().isoformat()
        now = datetime.now(timezone.utc).isoformat()
        with get_connection() as connection:
            healthy, warning, critical, unknown = self._status_counts(connection)
            score = _compute_health_score(
                healthy=healthy,
                warning=warning,
                critical=critical,
                unknown=unknown,
            )
            connection.execute(
                """
                INSERT OR REPLACE INTO trend_snapshots (
                  snapshot_date, healthy_count, warning_count, critical_count,
                  unknown_count, health_score, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (today, healthy, warning, critical, unknown, score, now),
            )
            connection.commit()

    def get_trend_snapshots(self, days: int) -> list[dict]:
        start_day = (datetime.now(timezone.utc).date() - timedelta(days=days - 1)).isoformat()
        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT snapshot_date, healthy_count, warning_count, critical_count, unknown_count, health_score
                FROM trend_snapshots
                WHERE snapshot_date >= ?
                ORDER BY snapshot_date ASC
                """,
                (start_day,),
            ).fetchall()
        return [
            {
                "snapshot_date": row["snapshot_date"],
                "healthy_count": row["healthy_count"],
                "warning_count": row["warning_count"],
                "critical_count": row["critical_count"],
                "unknown_count": row["unknown_count"],
                "health_score": row["health_score"],
            }
            for row in rows
        ]

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

    def get_alerts(self, *, limit: int, include_acknowledged: bool) -> list[dict]:
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

    def collect_mock_cycle(self) -> int:
        now = datetime.now(timezone.utc)
        rng = random.Random(int(now.timestamp()))

        with get_connection() as connection:
            rows = connection.execute(
                "SELECT integration_id, status, failed_instances, connection_errors, timeouts, aborted_runs, scheduled_runs_missed FROM integrations"
            ).fetchall()

            if not rows:
                return 0

            settings = {
                row["key"]: row["value"]
                for row in connection.execute("SELECT key, value FROM settings")
            }
            simulated_email_to = settings.get("notification_email", "ops-team@example.com")
            issue_warning = int(settings.get("threshold_issue_score_warning", "12"))
            issue_critical = int(settings.get("threshold_issue_score_critical", "18"))
            missed_warning = int(settings.get("threshold_missed_schedules_warning", "3"))
            missed_critical = int(settings.get("threshold_missed_schedules_critical", "5"))
            critical_count_warning = int(settings.get("threshold_critical_integrations_warning", "20"))
            critical_count_critical = int(settings.get("threshold_critical_integrations_critical", "35"))

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

                total_issue_score = failed + conn_errors + timeouts + aborted + missed
                should_create_alert = total_issue_score >= issue_warning
                if should_create_alert:
                    recent_window = (now - timedelta(minutes=45)).isoformat()
                    severity = "critical" if total_issue_score >= issue_critical else "warning"
                    existing = connection.execute(
                        """
                        SELECT id
                        FROM alert_events
                        WHERE integration_id = ?
                          AND metric_type = 'issue_score'
                          AND created_at >= ?
                        ORDER BY created_at DESC
                        LIMIT 1
                        """,
                        (row["integration_id"], recent_window),
                    ).fetchone()
                    if existing is None:
                        connection.execute(
                            """
                            INSERT INTO alert_events (
                              severity, integration_id, title, message, simulated_email_to, created_at, acknowledged
                              , metric_type, metric_value
                            ) VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)
                            """,
                            (
                                severity,
                                row["integration_id"],
                                "Integration issue score threshold breached",
                                f"{row['integration_id']} reached issue score {total_issue_score} in latest collector cycle.",
                                simulated_email_to,
                                now.isoformat(),
                                "issue_score",
                                total_issue_score,
                            ),
                        )

                if missed >= missed_warning:
                    schedule_severity = "critical" if missed >= missed_critical else "warning"
                    existing_schedule = connection.execute(
                        """
                        SELECT id
                        FROM alert_events
                        WHERE integration_id = ?
                          AND metric_type = 'missed_schedules'
                          AND created_at >= ?
                        ORDER BY created_at DESC
                        LIMIT 1
                        """,
                        (row["integration_id"], (now - timedelta(minutes=60)).isoformat()),
                    ).fetchone()
                    if existing_schedule is None:
                        connection.execute(
                            """
                            INSERT INTO alert_events (
                              severity, integration_id, title, message, simulated_email_to, created_at, acknowledged
                              , metric_type, metric_value
                            ) VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)
                            """,
                            (
                                schedule_severity,
                                row["integration_id"],
                                "Scheduler reliability warning",
                                f"{row['integration_id']} has {missed} missed schedules; investigate timing or upstream dependencies.",
                                simulated_email_to,
                                now.isoformat(),
                                "missed_schedules",
                                missed,
                            ),
                        )
                updated += 1

            cutoff = (now - timedelta(days=3)).isoformat()
            connection.execute("DELETE FROM run_events WHERE event_time < ?", (cutoff,))
            today = now.date().isoformat()
            healthy, warning, critical, unknown = self._status_counts(connection)

            if critical >= critical_count_warning:
                existing_system = connection.execute(
                    """
                    SELECT id
                    FROM alert_events
                    WHERE integration_id = 'SYSTEM'
                      AND metric_type = 'critical_integrations_count'
                      AND created_at >= ?
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    ((now - timedelta(minutes=60)).isoformat(),),
                ).fetchone()
                if existing_system is None:
                    severity = "critical" if critical >= critical_count_critical else "warning"
                    connection.execute(
                        """
                        INSERT INTO alert_events (
                          severity, integration_id, title, message, simulated_email_to, created_at, acknowledged,
                          metric_type, metric_value
                        ) VALUES (?, 'SYSTEM', ?, ?, ?, ?, 0, 'critical_integrations_count', ?)
                        """,
                        (
                            severity,
                            "Critical integration count threshold breached",
                            f"Critical integrations currently at {critical}, exceeding configured threshold.",
                            simulated_email_to,
                            now.isoformat(),
                            critical,
                        ),
                    )

            connection.execute(
                """
                INSERT OR REPLACE INTO trend_snapshots (
                  snapshot_date, healthy_count, warning_count, critical_count,
                  unknown_count, health_score, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    today,
                    healthy,
                    warning,
                    critical,
                    unknown,
                    _compute_health_score(
                        healthy=healthy,
                        warning=warning,
                        critical=critical,
                        unknown=unknown,
                    ),
                    now.isoformat(),
                ),
            )
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
