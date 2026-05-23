"""Regression tests for auth, protected settings, trends, alerts, and audit logging."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import requests


def _load_base_url() -> str:
    # Module: URL configuration sourced from frontend env for public endpoint verification
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


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or _load_base_url()


def _get_admin_credentials() -> tuple[str, str]:
    email = os.environ.get("TEST_ADMIN_EMAIL", "").strip()
    password = os.environ.get("TEST_ADMIN_PASSWORD", "").strip()
    if not email or not password:
        pytest.skip("Set TEST_ADMIN_EMAIL and TEST_ADMIN_PASSWORD to run authenticated test coverage")
    return email, password


@pytest.fixture()
def api_client() -> requests.Session:
    # Module: shared HTTP client for API regression checks
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture()
def admin_credentials() -> tuple[str, str]:
    return _get_admin_credentials()


@pytest.fixture()
def admin_token(api_client: requests.Session, admin_credentials: tuple[str, str]) -> str:
    # Module: auth bootstrap/login helper for protected endpoints
    admin_email, admin_password = admin_credentials

    status_response = api_client.get(f"{BASE_URL}/api/auth/status", timeout=20)
    assert status_response.status_code == 200
    status_data = status_response.json()

    if not status_data["has_admin"]:
        register_response = api_client.post(
            f"{BASE_URL}/api/auth/register-admin",
            json={"email": admin_email, "password": admin_password},
            timeout=20,
        )
        assert register_response.status_code == 200
        payload = register_response.json()
        assert payload["email"] == admin_email
        assert isinstance(payload["token"], str)
        assert len(payload["token"]) > 20
        return payload["token"]

    login_response = api_client.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": admin_email, "password": admin_password},
        timeout=20,
    )
    if login_response.status_code != 200:
        pytest.fail("Admin exists but required credentials failed login; cannot test protected flows")

    payload = login_response.json()
    assert payload["email"] == admin_email
    assert isinstance(payload["token"], str)
    assert len(payload["token"]) > 20
    return payload["token"]


def _audit_action_exists(api_client: requests.Session, token: str, action_type: str) -> bool:
    logs_response = api_client.get(
        f"{BASE_URL}/api/audit-logs?limit=120",
        headers={"Authorization": f"Bearer {token}"},
        timeout=20,
    )
    assert logs_response.status_code == 200
    logs = logs_response.json()
    return any(entry["action_type"] == action_type for entry in logs)


def test_auth_status_and_register_bootstrap_behavior(
    api_client: requests.Session, admin_credentials: tuple[str, str]
) -> None:
    # Feature: auth bootstrap status + register-admin behavior
    admin_email, admin_password = admin_credentials

    status_before = api_client.get(f"{BASE_URL}/api/auth/status", timeout=20)
    assert status_before.status_code == 200
    before_payload = status_before.json()
    assert before_payload["authenticated_email"] is None

    if before_payload["has_admin"] is False:
        register_response = api_client.post(
            f"{BASE_URL}/api/auth/register-admin",
            json={"email": admin_email, "password": admin_password},
            timeout=20,
        )
        assert register_response.status_code == 200
        register_payload = register_response.json()
        assert register_payload["email"] == admin_email
        assert isinstance(register_payload["token"], str)
        assert len(register_payload["token"]) > 20

        status_after = api_client.get(
            f"{BASE_URL}/api/auth/status",
            headers={"Authorization": f"Bearer {register_payload['token']}"},
            timeout=20,
        )
        assert status_after.status_code == 200
        after_payload = status_after.json()
        assert after_payload["has_admin"] is True
        assert after_payload["authenticated_email"] == admin_email
    else:
        register_reject = api_client.post(
            f"{BASE_URL}/api/auth/register-admin",
            json={"email": admin_email, "password": admin_password},
            timeout=20,
        )
        assert register_reject.status_code == 409


def test_login_failure_records_audit(
    api_client: requests.Session,
    admin_token: str,
    admin_credentials: tuple[str, str],
) -> None:
    # Feature: failed login returns 401 + audit entry
    admin_email, _ = admin_credentials

    failed_login = api_client.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": admin_email, "password": "WrongBadgerPass!"},
        timeout=20,
    )
    assert failed_login.status_code == 401
    data = failed_login.json()
    assert "detail" in data

    assert _audit_action_exists(api_client, admin_token, "login_failed") is True


def test_login_success_records_audit(
    api_client: requests.Session,
    admin_token: str,
    admin_credentials: tuple[str, str],
) -> None:
    # Feature: successful login returns token + audit entry
    admin_email, admin_password = admin_credentials

    success_login = api_client.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": admin_email, "password": admin_password},
        timeout=20,
    )
    assert success_login.status_code == 200
    payload = success_login.json()
    assert payload["email"] == admin_email
    assert isinstance(payload["token"], str)
    assert len(payload["token"]) > 20

    assert _audit_action_exists(api_client, payload["token"], "login_success") is True


def test_settings_endpoints_require_auth(api_client: requests.Session) -> None:
    # Feature: settings GET/PUT are protected by bearer token
    get_response = api_client.get(f"{BASE_URL}/api/settings", timeout=20)
    assert get_response.status_code == 401

    put_response = api_client.put(
        f"{BASE_URL}/api/settings",
        json={
            "oic_base_url": "https://unauthorized.example.com",
            "auth_mode": "OAuth2",
            "polling_seconds": 30,
            "notification_email": "unauthorized@example.com",
            "threshold_issue_score_warning": 12,
            "threshold_issue_score_critical": 18,
            "threshold_missed_schedules_warning": 3,
            "threshold_missed_schedules_critical": 5,
            "threshold_critical_integrations_warning": 20,
            "threshold_critical_integrations_critical": 35,
            "webhook_enabled": False,
            "webhook_url": "",
            "webhook_bearer_token": "",
            "webhook_max_retries": 3,
            "webhook_initial_backoff_seconds": 0.5,
            "webhook_timeout_seconds": 3,
        },
        timeout=20,
    )
    assert put_response.status_code == 401


def test_settings_persist_with_auth_and_log_audit(api_client: requests.Session, admin_token: str) -> None:
    # Feature: settings update persistence and settings_updated audit entry
    auth_headers = {"Authorization": f"Bearer {admin_token}"}

    original_response = api_client.get(f"{BASE_URL}/api/settings", headers=auth_headers, timeout=20)
    assert original_response.status_code == 200
    original_settings = original_response.json()

    update_payload = {
        "oic_base_url": "https://trend-alerts.example.com",
        "auth_mode": "API-Key",
        "polling_seconds": 55,
        "notification_email": "alerts-team@example.com",
        "threshold_issue_score_warning": original_settings["threshold_issue_score_warning"],
        "threshold_issue_score_critical": original_settings["threshold_issue_score_critical"],
        "threshold_missed_schedules_warning": original_settings["threshold_missed_schedules_warning"],
        "threshold_missed_schedules_critical": original_settings["threshold_missed_schedules_critical"],
        "threshold_critical_integrations_warning": original_settings[
            "threshold_critical_integrations_warning"
        ],
        "threshold_critical_integrations_critical": original_settings[
            "threshold_critical_integrations_critical"
        ],
        "webhook_enabled": original_settings["webhook_enabled"],
        "webhook_url": original_settings["webhook_url"],
        "webhook_bearer_token": original_settings["webhook_bearer_token"],
        "webhook_max_retries": original_settings["webhook_max_retries"],
        "webhook_initial_backoff_seconds": original_settings["webhook_initial_backoff_seconds"],
        "webhook_timeout_seconds": original_settings["webhook_timeout_seconds"],
    }
    update_response = api_client.put(
        f"{BASE_URL}/api/settings",
        json=update_payload,
        headers=auth_headers,
        timeout=20,
    )
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["oic_base_url"] == update_payload["oic_base_url"]
    assert updated["auth_mode"] == update_payload["auth_mode"]
    assert updated["polling_seconds"] == update_payload["polling_seconds"]
    assert updated["notification_email"] == update_payload["notification_email"]

    verify_response = api_client.get(f"{BASE_URL}/api/settings", headers=auth_headers, timeout=20)
    assert verify_response.status_code == 200
    persisted = verify_response.json()
    assert persisted["oic_base_url"] == update_payload["oic_base_url"]
    assert persisted["auth_mode"] == update_payload["auth_mode"]
    assert persisted["polling_seconds"] == update_payload["polling_seconds"]
    assert persisted["notification_email"] == update_payload["notification_email"]

    assert _audit_action_exists(api_client, admin_token, "settings_updated") is True

    restore_response = api_client.put(
        f"{BASE_URL}/api/settings",
        json=original_settings,
        headers=auth_headers,
        timeout=20,
    )
    assert restore_response.status_code == 200


def test_manual_collector_trigger_and_audit_entry(api_client: requests.Session, admin_token: str) -> None:
    # Feature: manual collector trigger works and writes manual_collector_trigger audit event
    run_response = api_client.post(
        f"{BASE_URL}/api/mock-collector/run",
        headers={"Authorization": f"Bearer {admin_token}"},
        timeout=30,
    )
    assert run_response.status_code == 200
    run_payload = run_response.json()
    assert isinstance(run_payload["updated_integrations"], int)
    assert run_payload["updated_integrations"] >= 25

    assert _audit_action_exists(api_client, admin_token, "manual_collector_trigger") is True


def test_trends_default_returns_30_day_window(api_client: requests.Session) -> None:
    # Feature: trend snapshots default to last 30 days
    response = api_client.get(f"{BASE_URL}/api/trends", timeout=20)
    assert response.status_code == 200
    rows = response.json()
    assert isinstance(rows, list)
    assert len(rows) == 30
    assert "snapshot_date" in rows[0]
    assert isinstance(rows[0]["health_score"], float)


def test_alerts_endpoint_returns_simulated_email_fields(api_client: requests.Session) -> None:
    # Feature: in-app alerts include simulated email log metadata
    response = api_client.get(f"{BASE_URL}/api/alerts?limit=20", timeout=20)
    assert response.status_code == 200
    alerts = response.json()
    assert isinstance(alerts, list)
    if not alerts:
        pytest.skip("No active alerts found; skipping simulated email field check")

    first_alert = alerts[0]
    assert "simulated_email_to" in first_alert
    assert isinstance(first_alert["simulated_email_to"], str)
    assert "@" in first_alert["simulated_email_to"]
    assert isinstance(first_alert["acknowledged"], bool)


def test_alert_acknowledge_requires_auth(api_client: requests.Session) -> None:
    # Feature: alert acknowledgement requires bearer auth
    alerts_response = api_client.get(f"{BASE_URL}/api/alerts?limit=1", timeout=20)
    assert alerts_response.status_code == 200
    alerts = alerts_response.json()
    if not alerts:
        pytest.skip("No active alerts available for auth-required acknowledge check")

    alert_id = alerts[0]["id"]
    acknowledge_response = api_client.post(f"{BASE_URL}/api/alerts/{alert_id}/acknowledge", timeout=20)
    assert acknowledge_response.status_code == 401


def test_alert_acknowledge_with_auth_updates_state_and_audit(
    api_client: requests.Session, admin_token: str
) -> None:
    # Feature: authenticated acknowledgement updates alert state + writes audit event
    auth_headers = {"Authorization": f"Bearer {admin_token}"}
    alerts_response = api_client.get(f"{BASE_URL}/api/alerts?limit=30", timeout=20)
    assert alerts_response.status_code == 200
    alerts = alerts_response.json()
    if not alerts:
        pytest.skip("No active alerts available for acknowledgement test")

    alert_id = alerts[0]["id"]

    acknowledge_response = api_client.post(
        f"{BASE_URL}/api/alerts/{alert_id}/acknowledge",
        headers=auth_headers,
        timeout=20,
    )
    assert acknowledge_response.status_code == 200
    acknowledge_payload = acknowledge_response.json()
    assert acknowledge_payload["status"] == "acknowledged"

    include_ack_response = api_client.get(
        f"{BASE_URL}/api/alerts?limit=50&include_acknowledged=true",
        timeout=20,
    )
    assert include_ack_response.status_code == 200
    updated_alerts = include_ack_response.json()
    matching = [item for item in updated_alerts if item["id"] == alert_id]
    assert matching, "Acknowledged alert should still be queryable with include_acknowledged=true"
    assert matching[0]["acknowledged"] is True

    assert _audit_action_exists(api_client, admin_token, "alert_acknowledged") is True


def test_audit_logs_endpoint_requires_auth(api_client: requests.Session) -> None:
    # Feature: audit logs endpoint is protected
    response = api_client.get(f"{BASE_URL}/api/audit-logs?limit=20", timeout=20)
    assert response.status_code == 401
