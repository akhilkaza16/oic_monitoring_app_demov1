from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from secrets import SystemRandom

from app.database import get_connection
from app.services.webhook_adapter import WebhookAdapter


def _compute_health_score(*, healthy: int, warning: int, critical: int, unknown: int) -> float:
    total = healthy + warning + critical + unknown
    if total == 0:
        return 0.0
    weighted = healthy * 1.0 + warning * 0.6 + critical * 0.2 + unknown * 0.4
    return round((weighted / total) * 100, 2)


@dataclass(frozen=True)
class CycleThresholds:
    simulated_email_to: str
    issue_warning: int
    issue_critical: int
    missed_warning: int
    missed_critical: int
    critical_count_warning: int
    critical_count_critical: int


class CollectorRepository:
    def __init__(self, webhook_adapter: WebhookAdapter | None = None) -> None:
        self.webhook_adapter = webhook_adapter

    def collect_mock_cycle(self) -> int:
        now = datetime.now(timezone.utc)
        rng = SystemRandom()

        with get_connection() as connection:
            rows = connection.execute(
                "SELECT integration_id, status, failed_instances, connection_errors, timeouts, aborted_runs, scheduled_runs_missed FROM integrations"
            ).fetchall()

            if not rows:
                return 0

            thresholds = self._load_thresholds(connection)
            target_rows = self._pick_target_rows(rows, rng)

            updated = 0
            for row in target_rows:
                self._process_row(
                    connection=connection,
                    row=row,
                    now=now,
                    rng=rng,
                    thresholds=thresholds,
                )
                updated += 1

            self._prune_run_events(connection, now)
            counts = self._status_counts(connection)
            self._ensure_system_critical_alert(connection, now, counts["critical"], thresholds)
            self._upsert_trend_snapshot(connection, now, counts)
            connection.commit()

        return updated

    def _load_thresholds(self, connection) -> CycleThresholds:
        settings = {
            row["key"]: row["value"]
            for row in connection.execute("SELECT key, value FROM settings")
        }
        return CycleThresholds(
            simulated_email_to=settings.get("notification_email", "ops-team@example.com"),
            issue_warning=int(settings.get("threshold_issue_score_warning", "12")),
            issue_critical=int(settings.get("threshold_issue_score_critical", "18")),
            missed_warning=int(settings.get("threshold_missed_schedules_warning", "3")),
            missed_critical=int(settings.get("threshold_missed_schedules_critical", "5")),
            critical_count_warning=int(settings.get("threshold_critical_integrations_warning", "20")),
            critical_count_critical=int(settings.get("threshold_critical_integrations_critical", "35")),
        )

    def _pick_target_rows(self, rows: list, rng: SystemRandom) -> list:
        sample_size = max(25, int(len(rows) * 0.2))
        return rng.sample(list(rows), k=min(sample_size, len(rows)))

    def _process_row(
        self,
        *,
        connection,
        row,
        now: datetime,
        rng: SystemRandom,
        thresholds: CycleThresholds,
    ) -> None:
        next_status = self._next_status(row["status"], rng)
        failed, conn_errors, timeouts, aborted, missed, success_rate = self._next_metrics(
            row=row,
            next_status=next_status,
            rng=rng,
        )

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

        error_type, message = self._run_event_message(next_status=next_status, rng=rng)
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
        self._create_issue_score_alert_if_needed(
            connection=connection,
            now=now,
            integration_id=row["integration_id"],
            issue_score=total_issue_score,
            thresholds=thresholds,
        )
        self._create_missed_schedule_alert_if_needed(
            connection=connection,
            now=now,
            integration_id=row["integration_id"],
            missed=missed,
            thresholds=thresholds,
        )

    def _next_status(self, current_status: str, rng: SystemRandom) -> str:
        return rng.choices(
            ["healthy", "warning", "critical", "unknown"],
            weights=self._transition_weights(current_status),
            k=1,
        )[0]

    def _next_metrics(self, *, row, next_status: str, rng: SystemRandom) -> tuple[int, int, int, int, int, float]:
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
        return failed, conn_errors, timeouts, aborted, missed, success_rate

    def _run_event_message(self, *, next_status: str, rng: SystemRandom) -> tuple[str | None, str]:
        if next_status == "healthy":
            return None, "Completed successfully"

        error_type = rng.choice(["ConnectionError", "Timeout", "RuntimeAbort", "MappingError"])
        return error_type, f"{error_type} generated during mock collector cycle"

    def _create_issue_score_alert_if_needed(
        self,
        *,
        connection,
        now: datetime,
        integration_id: str,
        issue_score: int,
        thresholds: CycleThresholds,
    ) -> None:
        if issue_score < thresholds.issue_warning:
            return

        exists = self._recent_alert_exists(
            connection=connection,
            integration_id=integration_id,
            metric_type="issue_score",
            window_iso=(now - timedelta(minutes=45)).isoformat(),
        )
        if exists:
            return

        severity = "critical" if issue_score >= thresholds.issue_critical else "warning"
        cursor = connection.execute(
            """
            INSERT INTO alert_events (
              severity, integration_id, title, message, simulated_email_to, created_at, acknowledged,
              metric_type, metric_value
            ) VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)
            """,
            (
                severity,
                integration_id,
                "Integration issue score threshold breached",
                f"{integration_id} reached issue score {issue_score} in latest collector cycle.",
                thresholds.simulated_email_to,
                now.isoformat(),
                "issue_score",
                issue_score,
            ),
        )
        self._send_webhook(
            severity=severity,
            integration_id=integration_id,
            title="Integration issue score threshold breached",
            event_time_iso=now.isoformat(),
            inserted_id=cursor.lastrowid,
        )

    def _create_missed_schedule_alert_if_needed(
        self,
        *,
        connection,
        now: datetime,
        integration_id: str,
        missed: int,
        thresholds: CycleThresholds,
    ) -> None:
        if missed < thresholds.missed_warning:
            return

        exists = self._recent_alert_exists(
            connection=connection,
            integration_id=integration_id,
            metric_type="missed_schedules",
            window_iso=(now - timedelta(minutes=60)).isoformat(),
        )
        if exists:
            return

        severity = "critical" if missed >= thresholds.missed_critical else "warning"
        cursor = connection.execute(
            """
            INSERT INTO alert_events (
              severity, integration_id, title, message, simulated_email_to, created_at, acknowledged,
              metric_type, metric_value
            ) VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)
            """,
            (
                severity,
                integration_id,
                "Scheduler reliability warning",
                f"{integration_id} has {missed} missed schedules; investigate timing or upstream dependencies.",
                thresholds.simulated_email_to,
                now.isoformat(),
                "missed_schedules",
                missed,
            ),
        )
        self._send_webhook(
            severity=severity,
            integration_id=integration_id,
            title="Scheduler reliability warning",
            event_time_iso=now.isoformat(),
            inserted_id=cursor.lastrowid,
        )

    def _ensure_system_critical_alert(
        self,
        connection,
        now: datetime,
        critical_count: int,
        thresholds: CycleThresholds,
    ) -> None:
        if critical_count < thresholds.critical_count_warning:
            return

        exists = self._recent_alert_exists(
            connection=connection,
            integration_id="SYSTEM",
            metric_type="critical_integrations_count",
            window_iso=(now - timedelta(minutes=60)).isoformat(),
        )
        if exists:
            return

        severity = (
            "critical"
            if critical_count >= thresholds.critical_count_critical
            else "warning"
        )
        cursor = connection.execute(
            """
            INSERT INTO alert_events (
              severity, integration_id, title, message, simulated_email_to, created_at, acknowledged,
              metric_type, metric_value
            ) VALUES (?, 'SYSTEM', ?, ?, ?, ?, 0, 'critical_integrations_count', ?)
            """,
            (
                severity,
                "Critical integration count threshold breached",
                f"Critical integrations currently at {critical_count}, exceeding configured threshold.",
                thresholds.simulated_email_to,
                now.isoformat(),
                critical_count,
            ),
        )
        self._send_webhook(
            severity=severity,
            integration_id="SYSTEM",
            title="Critical integration count threshold breached",
            event_time_iso=now.isoformat(),
            inserted_id=cursor.lastrowid,
        )

    def _recent_alert_exists(
        self,
        *,
        connection,
        integration_id: str,
        metric_type: str,
        window_iso: str,
    ) -> bool:
        existing = connection.execute(
            """
            SELECT id
            FROM alert_events
            WHERE integration_id = ?
              AND metric_type = ?
              AND created_at >= ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (integration_id, metric_type, window_iso),
        ).fetchone()
        return existing is not None

    def _prune_run_events(self, connection, now: datetime) -> None:
        cutoff = (now - timedelta(days=3)).isoformat()
        connection.execute("DELETE FROM run_events WHERE event_time < ?", (cutoff,))

    def _status_counts(self, connection) -> dict[str, int]:
        grouped_rows = connection.execute(
            "SELECT status, COUNT(*) AS count FROM integrations GROUP BY status"
        ).fetchall()
        grouped = {row["status"]: row["count"] for row in grouped_rows}
        return {
            "healthy": grouped.get("healthy", 0),
            "warning": grouped.get("warning", 0),
            "critical": grouped.get("critical", 0),
            "unknown": grouped.get("unknown", 0),
        }

    def _upsert_trend_snapshot(self, connection, now: datetime, counts: dict[str, int]) -> None:
        connection.execute(
            """
            INSERT OR REPLACE INTO trend_snapshots (
              snapshot_date, healthy_count, warning_count, critical_count,
              unknown_count, health_score, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                now.date().isoformat(),
                counts["healthy"],
                counts["warning"],
                counts["critical"],
                counts["unknown"],
                _compute_health_score(
                    healthy=counts["healthy"],
                    warning=counts["warning"],
                    critical=counts["critical"],
                    unknown=counts["unknown"],
                ),
                now.isoformat(),
            ),
        )

    @staticmethod
    def _transition_weights(current_status: str) -> list[float]:
        if current_status == "healthy":
            return [0.75, 0.18, 0.04, 0.03]
        if current_status == "warning":
            return [0.28, 0.48, 0.18, 0.06]
        if current_status == "critical":
            return [0.18, 0.34, 0.40, 0.08]
        return [0.30, 0.25, 0.25, 0.20]

    def _send_webhook(
        self,
        *,
        severity: str,
        integration_id: str,
        title: str,
        event_time_iso: str,
        inserted_id: int | None,
    ) -> None:
        if not self.webhook_adapter or inserted_id is None:
            return
        try:
            threading.Thread(
                target=self.webhook_adapter.send_alert_event,
                kwargs={
                    "severity": severity,
                    "integration_id": integration_id,
                    "alert_title": title,
                    "event_time_iso": event_time_iso,
                },
                daemon=True,
            ).start()
        except Exception:
            pass
