from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from app.database import get_connection


def _compute_health_score(*, healthy: int, warning: int, critical: int, unknown: int) -> float:
    total = healthy + warning + critical + unknown
    if total == 0:
        return 0.0
    weighted = healthy * 1.0 + warning * 0.6 + critical * 0.2 + unknown * 0.4
    return round((weighted / total) * 100, 2)


class CollectorRepository:
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
            grouped_rows = connection.execute(
                "SELECT status, COUNT(*) AS count FROM integrations GROUP BY status"
            ).fetchall()
            grouped = {row["status"]: row["count"] for row in grouped_rows}
            healthy = grouped.get("healthy", 0)
            warning = grouped.get("warning", 0)
            critical = grouped.get("critical", 0)
            unknown = grouped.get("unknown", 0)

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
                    now.date().isoformat(),
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
