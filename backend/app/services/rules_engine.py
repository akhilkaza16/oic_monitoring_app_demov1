from __future__ import annotations

from app.models import Recommendation


def build_recommendations(
    *,
    status: str,
    failed_instances: int,
    connection_errors: int,
    timeouts: int,
    aborted_runs: int,
    scheduled_runs_missed: int,
) -> list[Recommendation]:
    candidates: list[tuple[int, str, str, str]] = []

    if connection_errors > 0:
        score = 100 + connection_errors * 7
        candidates.append(
            (
                score,
                "Stabilize upstream/downstream connections",
                "Connection error spikes often indicate expired credentials, DNS drift, or endpoint throttling.",
                "Validate credentials and certificates, then run a connection smoke test every 5 minutes.",
            )
        )

    if timeouts > 0:
        score = 90 + timeouts * 6
        candidates.append(
            (
                score,
                "Reduce timeout pressure",
                "Repeated timeouts suggest long-running payload transformation or overloaded target APIs.",
                "Increase async chunking and tune retry backoff; add payload size guardrails.",
            )
        )

    if failed_instances > 0:
        score = 80 + failed_instances * 5
        candidates.append(
            (
                score,
                "Prioritize failed-instance replay",
                "Higher failed-instance count directly degrades business process completion.",
                "Replay failed instances in batches and isolate recurring payload signatures.",
            )
        )

    if aborted_runs > 0:
        score = 70 + aborted_runs * 4
        candidates.append(
            (
                score,
                "Investigate runtime aborts",
                "Aborts usually occur when dependency services return invalid responses or workflows terminate early.",
                "Enable step-level tracing and add defensive checks before terminal actions.",
            )
        )

    if scheduled_runs_missed > 0:
        score = 60 + scheduled_runs_missed * 8
        candidates.append(
            (
                score,
                "Repair scheduler reliability",
                "Missed schedule windows can create downstream data gaps and reporting delays.",
                "Audit scheduler timezone/clock drift and set synthetic heartbeat alerts.",
            )
        )

    if not candidates and status == "healthy":
        candidates.append(
            (
                1,
                "No immediate action required",
                "This integration is currently stable with low failure indicators.",
                "Keep standard monitoring enabled and review trendline weekly.",
            )
        )

    candidates.sort(key=lambda item: item[0], reverse=True)

    recommendations: list[Recommendation] = []
    for index, (_, title, rationale, action) in enumerate(candidates[:3], start=1):
        recommendations.append(
            Recommendation(
                priority=index,
                title=title,
                rationale=rationale,
                action=action,
            )
        )

    return recommendations
