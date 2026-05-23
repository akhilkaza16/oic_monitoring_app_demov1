"""Targeted tests for webhook delivery log API summary/filter contracts and settings guardrails."""

from __future__ import annotations

import os
import time
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
    # Module: common HTTP client for webhook delivery log and settings guardrail contract checks
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture()
def admin_token(api_client: requests.Session) -> str:
    # Module: admin auth token bootstrap/login for protected settings + notifications endpoints
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
        return register_response.json()["token"]

    login_response = api_client.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=20,
    )
    assert login_response.status_code == 200
    return login_response.json()["token"]


def test_settings_guardrails_reject_out_of_range_webhook_retry_policy(
    api_client: requests.Session, admin_token: str
) -> None:
    # Feature: settings API enforces conservative retry policy bounds (retries/backoff/timeout)
    headers = {"Authorization": f"Bearer {admin_token}"}
    current = api_client.get(f"{BASE_URL}/api/settings", headers=headers, timeout=20)
    assert current.status_code == 200
    baseline = current.json()

    invalid_payload = {
        **baseline,
        "webhook_max_retries": 4,
        "webhook_initial_backoff_seconds": 0.2,
        "webhook_timeout_seconds": 7,
    }
    invalid_response = api_client.put(f"{BASE_URL}/api/settings", json=invalid_payload, headers=headers, timeout=20)
    assert invalid_response.status_code == 422
    detail = str(invalid_response.json().get("detail"))
    assert "webhook_max_retries" in detail


def test_webhook_delivery_logs_returns_summary_and_filtered_items(
    api_client: requests.Session, admin_token: str
) -> None:
    # Feature: webhook delivery logs endpoint returns summary counters and supports status filtering
    headers = {"Authorization": f"Bearer {admin_token}"}
    settings_response = api_client.get(f"{BASE_URL}/api/settings", headers=headers, timeout=20)
    assert settings_response.status_code == 200
    original = settings_response.json()

    try:
        update_payload = {
            **original,
            "threshold_issue_score_warning": 1,
            "threshold_issue_score_critical": 2,
            "threshold_missed_schedules_warning": 1,
            "threshold_missed_schedules_critical": 2,
            "threshold_critical_integrations_warning": 1,
            "threshold_critical_integrations_critical": 2,
            "webhook_enabled": True,
            "webhook_url": "https://127.0.0.1:1/unreachable",
            "webhook_bearer_token": "test-token-for-log-generation",
            "webhook_max_retries": 3,
            "webhook_initial_backoff_seconds": 0.5,
            "webhook_timeout_seconds": 2,
        }
        update_response = api_client.put(f"{BASE_URL}/api/settings", json=update_payload, headers=headers, timeout=20)
        assert update_response.status_code == 200

        collector_response = api_client.post(f"{BASE_URL}/api/mock-collector/run", headers=headers, timeout=40)
        assert collector_response.status_code == 200
        assert collector_response.json()["updated_integrations"] >= 25

        time.sleep(3)

        all_response = api_client.get(
            f"{BASE_URL}/api/webhook-delivery-logs?status=all&limit=80", headers=headers, timeout=20
        )
        assert all_response.status_code == 200
        all_payload = all_response.json()
        assert set(all_payload.keys()) == {"summary", "items"}
        assert set(all_payload["summary"].keys()) == {"success", "failed", "total"}
        assert isinstance(all_payload["items"], list)
        assert all_payload["summary"]["total"] >= all_payload["summary"]["failed"]
        assert all_payload["summary"]["total"] >= all_payload["summary"]["success"]

        failed_response = api_client.get(
            f"{BASE_URL}/api/webhook-delivery-logs?status=failed&limit=80", headers=headers, timeout=20
        )
        assert failed_response.status_code == 200
        failed_items = failed_response.json()["items"]
        assert isinstance(failed_items, list)
        for item in failed_items:
            assert item["status"] == "failed"
            assert "attempts" in item
            assert "created_at" in item
    finally:
        restore_response = api_client.put(f"{BASE_URL}/api/settings", json=original, headers=headers, timeout=20)
        assert restore_response.status_code == 200
