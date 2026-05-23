from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.database import get_connection


def _compute_health_score(*, healthy: int, warning: int, critical: int, unknown: int) -> float:
    total = healthy + warning + critical + unknown
    if total == 0:
        return 0.0
    weighted = healthy * 1.0 + warning * 0.6 + critical * 0.2 + unknown * 0.4
    return round((weighted / total) * 100, 2)


class TrendsRepository:
    def get_trend_snapshots(self, days: int):
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

    def record_daily_snapshot(self) -> None:
        with get_connection() as connection:
            grouped_rows = connection.execute(
                "SELECT status, COUNT(*) AS count FROM integrations GROUP BY status"
            ).fetchall()
            grouped = {row["status"]: row["count"] for row in grouped_rows}
            healthy = grouped.get("healthy", 0)
            warning = grouped.get("warning", 0)
            critical = grouped.get("critical", 0)
            unknown = grouped.get("unknown", 0)

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
                (
                    datetime.now(timezone.utc).date().isoformat(),
                    healthy,
                    warning,
                    critical,
                    unknown,
                    score,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            connection.commit()
