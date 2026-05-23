"""Regression tests for configurable threshold settings, alert generation, and visibility filtering."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import requests


def _load_base_url() -> str:
    env_path = Path("/app/frontend/.env")
    if not env_path.exists():
        pytest.fail("Missing /app/frontend/.env; cannot resolve REACT_APP_BACKEND_URL")

    value: str | None = None
    for line in env_path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("REACT_APP_BACKEND_URL="):
            value = stripped.split("=", 1)[1].strip()
            break

    if not value:
        pytest.fail("REACT_APP_BACKEND_URL missing in /app/frontend/.env")
    return value.rstrip("/")


def _load_test_credentials() -> tuple[str, str]:
    creds_path = Path("/app/memory/test_credentials.md")
    if not creds_path.exists():
        pytest.fail("Missing /app/memory/test_credentials.md for auth testing")

    email: str | None = None
    password: str | None = None

    for line in creds_path.read_text().splitlines():
        text = line.strip()
        if text.startswith("- Admin Email:"):
            email = text.split(":", 1)[1].strip()
        if text.startswith("- Admin Password:"):
            password = text.split(":", 1)[1].strip()

    if not email or not password:
        pytest.fail("Admin credentials missing in /app/memory/test_credentials.md")

    return email, password


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or _load_base_url()
ADMIN_EMAIL, ADMIN_PASSWORD = _load_test_credentials()


@pytest.fixture()
def api_client() -> requests.Session:
    # Module: common HTTP client for threshold + settings + alert workflows
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture()
def admin_token(api_client: requests.Session) -> str:
    # Module: authenticated admin token for protected settings and audit endpoints
    status_response = api_client.get(f"{BASE_URL}/api/auth/status", timeout=20)
    assert status_response.status_code == 200
    status_payload = status_response.json()

    if not status_payload["has_admin"]:
        register_response = api_client.post(
            f"{BASE_URL}/api/auth/register-admin",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=20,
        )
        assert register_response.status_code == 200
        token = register_response.json()["token"]
    else:
        login_response = api_client.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=20,
        )
        if login_response.status_code != 200:
            pytest.skip("Skipping authenticated flows: admin login failed with provided credentials")
        token = login_response.json()["token"]

    assert isinstance(token, str)
    assert len(token) > 20
    return token


def _settings_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_settings_get_returns_all_threshold_fields(api_client: requests.Session, admin_token: str) -> None:
    # Feature: settings API returns full threshold payload used by settings UI
    response = api_client.get(f"{BASE_URL}/api/settings", headers=_settings_headers(admin_token), timeout=20)
    assert response.status_code == 200
    data = response.json()

    expected_keys = {
        "oic_base_url",
        "auth_mode",
        "polling_seconds",
        "notification_email",
        "threshold_issue_score_warning",
        "threshold_issue_score_critical",
        "threshold_missed_schedules_warning",
        "threshold_missed_schedules_critical",
        "threshold_critical_integrations_warning",
        "threshold_critical_integrations_critical",
        "webhook_enabled",
        "webhook_url",
        "webhook_bearer_token",
    }
    assert expected_keys.issubset(set(data.keys()))
    assert isinstance(data["threshold_issue_score_warning"], int)
    assert isinstance(data["threshold_issue_score_critical"], int)


def test_settings_update_persists_thresholds_and_writes_audit(api_client: requests.Session, admin_token: str) -> None:
    # Feature: threshold updates persist and audit logs include settings_updated events
    headers = _settings_headers(admin_token)
    before_response = api_client.get(f"{BASE_URL}/api/settings", headers=headers, timeout=20)
    assert before_response.status_code == 200
    original = before_response.json()

    update_payload = {
        **original,
        "threshold_issue_score_warning": 11,
        "threshold_issue_score_critical": 17,
        "threshold_missed_schedules_warning": 2,
        "threshold_missed_schedules_critical": 4,
        "threshold_critical_integrations_warning": 15,
        "threshold_critical_integrations_critical": 28,
    }

    update_response = api_client.put(f"{BASE_URL}/api/settings", json=update_payload, headers=headers, timeout=20)
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["threshold_issue_score_warning"] == 11
    assert updated["threshold_issue_score_critical"] == 17
    assert updated["threshold_missed_schedules_warning"] == 2
    assert updated["threshold_missed_schedules_critical"] == 4
    assert updated["threshold_critical_integrations_warning"] == 15
    assert updated["threshold_critical_integrations_critical"] == 28

    persisted_response = api_client.get(f"{BASE_URL}/api/settings", headers=headers, timeout=20)
    assert persisted_response.status_code == 200
    persisted = persisted_response.json()
    assert persisted["threshold_issue_score_warning"] == 11
    assert persisted["threshold_issue_score_critical"] == 17
    assert persisted["threshold_missed_schedules_warning"] == 2
    assert persisted["threshold_missed_schedules_critical"] == 4
    assert persisted["threshold_critical_integrations_warning"] == 15
    assert persisted["threshold_critical_integrations_critical"] == 28

    logs_response = api_client.get(f"{BASE_URL}/api/audit-logs?limit=120", headers=headers, timeout=20)
    assert logs_response.status_code == 200
    logs = logs_response.json()
    assert any(log["action_type"] == "settings_updated" for log in logs)

    restore_response = api_client.put(f"{BASE_URL}/api/settings", json=original, headers=headers, timeout=20)
    assert restore_response.status_code == 200


@pytest.mark.parametrize(
    "warning_key,critical_key,invalid_warning,invalid_critical,detail_substring",
    [
        (
            "threshold_issue_score_warning",
            "threshold_issue_score_critical",
            11,
            10,
            "Issue score warning threshold must be <= critical threshold",
        ),
        (
            "threshold_missed_schedules_warning",
            "threshold_missed_schedules_critical",
            6,
            5,
            "Missed schedules warning threshold must be <= critical threshold",
        ),
        (
            "threshold_critical_integrations_warning",
            "threshold_critical_integrations_critical",
            51,
            50,
            "Critical integration count warning threshold must be <= critical threshold",
        ),
    ],
)
def test_threshold_validation_enforces_warning_lte_critical(
    api_client: requests.Session,
    admin_token: str,
    warning_key: str,
    critical_key: str,
    invalid_warning: int,
    invalid_critical: int,
    detail_substring: str,
) -> None:
    # Feature: threshold validation blocks warning values above critical values for all pairs
    headers = _settings_headers(admin_token)
    base_response = api_client.get(f"{BASE_URL}/api/settings", headers=headers, timeout=20)
    assert base_response.status_code == 200
    payload = base_response.json()

    payload[warning_key] = invalid_warning
    payload[critical_key] = invalid_critical
    invalid_response = api_client.put(f"{BASE_URL}/api/settings", json=payload, headers=headers, timeout=20)
    assert invalid_response.status_code == 400
    body = invalid_response.json()
    assert detail_substring in body["detail"]


def test_collector_alerts_and_dashboard_visibility_follow_thresholds(
    api_client: requests.Session, admin_token: str
) -> None:
    # Feature: collector-generated alerts and dashboard alerts feed honor configured warning thresholds
    headers = _settings_headers(admin_token)
    settings_response = api_client.get(f"{BASE_URL}/api/settings", headers=headers, timeout=20)
    assert settings_response.status_code == 200
    original = settings_response.json()

    try:
        strict_payload = {
            **original,
            "threshold_issue_score_warning": 200,
            "threshold_issue_score_critical": 250,
            "threshold_missed_schedules_warning": 30,
            "threshold_missed_schedules_critical": 60,
            "threshold_critical_integrations_warning": 170,
            "threshold_critical_integrations_critical": 170,
        }
        strict_update = api_client.put(f"{BASE_URL}/api/settings", json=strict_payload, headers=headers, timeout=20)
        assert strict_update.status_code == 200

        collector_response = api_client.post(
            f"{BASE_URL}/api/mock-collector/run",
            headers=headers,
            timeout=30,
        )
        assert collector_response.status_code == 200
        collector_payload = collector_response.json()
        assert collector_payload["updated_integrations"] >= 25

        strict_alerts = api_client.get(f"{BASE_URL}/api/alerts?limit=50", timeout=20)
        assert strict_alerts.status_code == 200
        strict_rows = strict_alerts.json()
        for row in strict_rows:
            metric_type = row.get("metric_type")
            metric_value = row.get("metric_value")
            if metric_type == "issue_score" and metric_value is not None:
                assert metric_value >= 200
            if metric_type == "missed_schedules" and metric_value is not None:
                assert metric_value >= 30
            if metric_type == "critical_integrations_count" and metric_value is not None:
                assert metric_value >= 170

        strict_count = len(strict_rows)

        permissive_payload = {
            **original,
            "threshold_issue_score_warning": 1,
            "threshold_issue_score_critical": 2,
            "threshold_missed_schedules_warning": 1,
            "threshold_missed_schedules_critical": 2,
            "threshold_critical_integrations_warning": 1,
            "threshold_critical_integrations_critical": 2,
        }
        permissive_update = api_client.put(f"{BASE_URL}/api/settings", json=permissive_payload, headers=headers, timeout=20)
        assert permissive_update.status_code == 200

        collector_response_2 = api_client.post(
            f"{BASE_URL}/api/mock-collector/run",
            headers=headers,
            timeout=30,
        )
        assert collector_response_2.status_code == 200

        visible_alerts = api_client.get(f"{BASE_URL}/api/alerts?limit=50", timeout=20)
        assert visible_alerts.status_code == 200
        visible_rows = visible_alerts.json()
        assert len(visible_rows) >= strict_count
        assert all("metric_type" in row for row in visible_rows)

        assert any(
            (
                (row.get("metric_type") == "issue_score" and row.get("metric_value") is not None and row["metric_value"] < 200)
                or (
                    row.get("metric_type") == "missed_schedules"
                    and row.get("metric_value") is not None
                    and row["metric_value"] < 30
                )
                or (
                    row.get("metric_type") == "critical_integrations_count"
                    and row.get("metric_value") is not None
                    and row["metric_value"] < 170
                )
            )
            for row in visible_rows
        )
    finally:
        restore_response = api_client.put(f"{BASE_URL}/api/settings", json=original, headers=headers, timeout=20)
        assert restore_response.status_code == 200


def test_no_regression_for_dashboard_summary_and_integrations_list(api_client: requests.Session) -> None:
    # Feature: dashboard pages still backed by functioning summary, trends, and integrations APIs
    summary_response = api_client.get(f"{BASE_URL}/api/executive-summary", timeout=20)
    assert summary_response.status_code == 200
    summary = summary_response.json()
    assert summary["total_integrations"] == 170

    trend_response = api_client.get(f"{BASE_URL}/api/trends?days=30", timeout=20)
    assert trend_response.status_code == 200
    trends = trend_response.json()
    assert len(trends) == 30

    integrations_response = api_client.get(f"{BASE_URL}/api/integrations?limit=10&offset=0", timeout=20)
    assert integrations_response.status_code == 200
    integrations = integrations_response.json()
    assert integrations["limit"] == 10
    assert len(integrations["items"]) == 10
