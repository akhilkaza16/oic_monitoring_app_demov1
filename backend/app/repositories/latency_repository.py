from __future__ import annotations

from datetime import datetime, timezone

from app.database import get_connection


class LatencyRepository:
    def log_latency(self, *, endpoint: str, method: str, latency_ms: float) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with get_connection() as connection:
            connection.execute(
                "INSERT INTO latency_logs (endpoint, method, latency_ms, created_at) VALUES (?, ?, ?, ?)",
                (endpoint, method, round(latency_ms, 2), now),
            )
            connection.commit()

    def get_latency_logs(self, *, endpoint: str | None, limit: int):
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
