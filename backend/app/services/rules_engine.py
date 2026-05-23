from __future__ import annotations

from app.models import Recommendation


RECOMMENDATION_RULES: tuple[tuple[str, int, int, str, str, str], ...] = (
    (
        "connection_errors",
        100,
        7,
        "Stabilize upstream/downstream connections",
        "Connection error spikes often indicate expired credentials, DNS drift, or endpoint throttling.",
        "Validate credentials and certificates, then run a connection smoke test every 5 minutes.",
    ),
    (
        "timeouts",
        90,
        6,
        "Reduce timeout pressure",
        "Repeated timeouts suggest long-running payload transformation or overloaded target APIs.",
        "Increase async chunking and tune retry backoff; add payload size guardrails.",
    ),
    (
        "failed_instances",
        80,
        5,
        "Prioritize failed-instance replay",
        "Higher failed-instance count directly degrades business process completion.",
        "Replay failed instances in batches and isolate recurring payload signatures.",
    ),
    (
        "aborted_runs",
        70,
        4,
        "Investigate runtime aborts",
        "Aborts usually occur when dependency services return invalid responses or workflows terminate early.",
        "Enable step-level tracing and add defensive checks before terminal actions.",
    ),
    (
        "scheduled_runs_missed",
        60,
        8,
        "Repair scheduler reliability",
        "Missed schedule windows can create downstream data gaps and reporting delays.",
        "Audit scheduler timezone/clock drift and set synthetic heartbeat alerts.",
    ),
)


def _build_candidates(*, status: str, metrics: dict[str, int]) -> list[tuple[int, str, str, str]]:
    candidates: list[tuple[int, str, str, str]] = []
    for metric_name, base_score, multiplier, title, rationale, action in RECOMMENDATION_RULES:
        metric_value = metrics[metric_name]
        if metric_value <= 0:
            continue
        score = base_score + metric_value * multiplier
        candidates.append((score, title, rationale, action))

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
    return candidates


def build_recommendations(
    *,
    status: str,
    failed_instances: int,
    connection_errors: int,
    timeouts: int,
    aborted_runs: int,
    scheduled_runs_missed: int,
) -> list[Recommendation]:
    candidates = _build_candidates(
        status=status,
        metrics={
            "failed_instances": failed_instances,
            "connection_errors": connection_errors,
            "timeouts": timeouts,
            "aborted_runs": aborted_runs,
            "scheduled_runs_missed": scheduled_runs_missed,
        },
    )

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
