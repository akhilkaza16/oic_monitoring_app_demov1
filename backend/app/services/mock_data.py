from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

PROJECTS = [
    "Finance-Core",
    "Supply-Chain",
    "Retail-Experience",
    "HR-Operations",
    "Customer-360",
    "Data-Hub",
    "Compliance",
    "Partner-Exchange",
    "Payments",
    "Fulfillment",
]

BUSINESS_DOMAINS = [
    "ERP",
    "CRM",
    "HCM",
    "E-Commerce",
    "Logistics",
    "Data Warehouse",
    "Risk",
    "Procurement",
]

OWNERS = [
    "Avery Collins",
    "Jordan Patel",
    "Noah Rivera",
    "Riley Brooks",
    "Cameron Ellis",
    "Taylor Reed",
    "Sydney Martin",
    "Morgan Gray",
]

ERROR_TYPES = [
    "None",
    "ConnectionError",
    "Timeout",
    "MappingError",
    "ScheduleMiss",
    "RuntimeAbort",
]

STATUS_WEIGHTS = {
    "healthy": 0.56,
    "warning": 0.25,
    "critical": 0.14,
    "unknown": 0.05,
}


def _weighted_status(rng: random.Random) -> str:
    statuses = list(STATUS_WEIGHTS.keys())
    weights = list(STATUS_WEIGHTS.values())
    return rng.choices(statuses, weights=weights, k=1)[0]


def build_seed_dataset(total: int = 170) -> tuple[list[dict], list[dict], dict[str, str]]:
    rng = random.Random(170)
    now = datetime.now(timezone.utc)
    integrations: list[dict] = []
    run_events: list[dict] = []

    for index in range(1, total + 1):
        status = _weighted_status(rng)
        failed = rng.randint(0, 1)
        conn_errors = rng.randint(0, 1)
        timeouts = rng.randint(0, 1)
        aborted = rng.randint(0, 1)
        schedule_missed = rng.randint(0, 1)

        if status == "warning":
            failed += rng.randint(2, 6)
            conn_errors += rng.randint(1, 3)
            timeouts += rng.randint(1, 4)
            aborted += rng.randint(0, 2)
            schedule_missed += rng.randint(0, 2)
        elif status == "critical":
            failed += rng.randint(5, 14)
            conn_errors += rng.randint(2, 6)
            timeouts += rng.randint(2, 8)
            aborted += rng.randint(1, 4)
            schedule_missed += rng.randint(1, 4)
        elif status == "unknown":
            conn_errors += rng.randint(0, 2)
            timeouts += rng.randint(0, 2)

        penalty = failed * 1.5 + conn_errors * 2 + timeouts * 1.2 + aborted + schedule_missed
        success_rate = max(65.0, min(99.6, 99.8 - penalty))
        last_run_at = now - timedelta(minutes=rng.randint(0, 55), seconds=rng.randint(0, 59))

        integration_id = f"INTG-{index:03d}"
        integration = {
            "integration_id": integration_id,
            "name": f"{rng.choice(['Order', 'Invoice', 'Payroll', 'Shipment', 'Catalog', 'Customer', 'Supplier'])}-{index:03d}",
            "project": rng.choice(PROJECTS),
            "business_domain": rng.choice(BUSINESS_DOMAINS),
            "owner": rng.choice(OWNERS),
            "endpoint_url": f"https://oic.mock.local/integration/{integration_id.lower()}",
            "status": status,
            "failed_instances": failed,
            "connection_errors": conn_errors,
            "timeouts": timeouts,
            "aborted_runs": aborted,
            "scheduled_runs_missed": schedule_missed,
            "success_rate": round(success_rate, 2),
            "last_run_at": last_run_at.isoformat(),
        }
        integrations.append(integration)

        for event_index in range(10):
            event_time = last_run_at - timedelta(minutes=event_index * rng.randint(3, 7))
            event_status = status if event_index == 0 else _weighted_status(rng)
            error_type = rng.choice(ERROR_TYPES)
            if event_status == "healthy":
                error_type = "None"
            message = (
                "Completed successfully"
                if event_status == "healthy"
                else f"{error_type} detected while processing payload"
            )
            run_events.append(
                {
                    "integration_id": integration_id,
                    "event_time": event_time.isoformat(),
                    "run_status": event_status,
                    "duration_ms": rng.randint(240, 5200),
                    "error_type": None if error_type == "None" else error_type,
                    "message": message,
                }
            )

    settings = {
        "oic_base_url": "https://future-oic-host.example.com",
        "auth_mode": "OAuth2",
        "polling_seconds": "30",
        "notification_email": "ops-team@example.com",
    }

    return integrations, run_events, settings
