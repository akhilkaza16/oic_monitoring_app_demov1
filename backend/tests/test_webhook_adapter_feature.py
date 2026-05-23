"""Regression tests for webhook adapter settings, payload contract, and retry logic."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest
import requests

sys.path.insert(0, "/app/backend")

from app.database import get_connection
from app.repositories.collector_repository import CollectorRepository
from app.repositories.settings_repository import SettingsRepository
from app.services.webhook_adapter import WebhookAdapter


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
    # Module: shared HTTP client for settings API webhook contract checks
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture()
def admin_token(api_client: requests.Session) -> str:
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


def _latest_webhook_delivery_log() -> dict | None:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT id, event_type, severity, status, attempts, http_status, error_message
            FROM webhook_delivery_logs
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
    return dict(row) if row else None


def _webhook_log_count() -> int:
    with get_connection() as connection:
        return int(connection.execute("SELECT COUNT(*) FROM webhook_delivery_logs").fetchone()[0])


def test_settings_api_webhook_fields_and_required_validation(
    api_client: requests.Session, admin_token: str
) -> None:
    # Feature: settings API includes webhook fields and enforces URL/token requirement when enabled
    headers = {"Authorization": f"Bearer {admin_token}"}

    current = api_client.get(f"{BASE_URL}/api/settings", headers=headers, timeout=20)
    assert current.status_code == 200
    current_payload = current.json()
    assert "webhook_enabled" in current_payload
    assert "webhook_url" in current_payload
    assert "webhook_bearer_token" in current_payload
    assert "webhook_max_retries" in current_payload
    assert "webhook_initial_backoff_seconds" in current_payload
    assert "webhook_timeout_seconds" in current_payload

    invalid_payload = {**current_payload, "webhook_enabled": True, "webhook_url": "", "webhook_bearer_token": ""}
    invalid_response = api_client.put(f"{BASE_URL}/api/settings", json=invalid_payload, headers=headers, timeout=20)
    assert invalid_response.status_code == 400
    assert "Webhook URL and bearer token are required" in invalid_response.json()["detail"]


def test_webhook_adapter_retries_three_times_with_backoff_and_logs_failed_delivery(monkeypatch) -> None:
    # Feature: webhook adapter retries failed delivery up to 3 attempts with backoff and failed log row
    settings_repo = SettingsRepository()
    adapter = WebhookAdapter(settings_repo)

    settings_repo.upsert_settings(
        type("Payload", (), {
            "oic_base_url": "https://oic.local",
            "auth_mode": "OAuth2",
            "polling_seconds": 30,
            "notification_email": "ops@example.com",
            "threshold_issue_score_warning": 12,
            "threshold_issue_score_critical": 18,
            "threshold_missed_schedules_warning": 3,
            "threshold_missed_schedules_critical": 5,
            "threshold_critical_integrations_warning": 20,
            "threshold_critical_integrations_critical": 35,
            "webhook_enabled": True,
            "webhook_url": "https://127.0.0.1:1/unreachable",
            "webhook_bearer_token": "token-abc",
            "webhook_max_retries": 3,
            "webhook_initial_backoff_seconds": 0.5,
            "webhook_timeout_seconds": 3,
        })()
    )

    post_calls: list[dict] = []
    sleep_calls: list[float] = []

    def _raise_request_exception(url, json, headers, timeout):
        post_calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        raise requests.RequestException("simulated network error")

    monkeypatch.setattr("app.services.webhook_adapter.requests.post", _raise_request_exception)
    monkeypatch.setattr("app.services.webhook_adapter.time.sleep", lambda seconds: sleep_calls.append(seconds))

    adapter.send_alert_event(
        severity="critical",
        integration_id="INTG-999",
        alert_title="Collector generated critical",
        event_time_iso="2026-02-15T12:00:00+00:00",
    )

    assert len(post_calls) == 3
    assert sleep_calls == [0.5, 1.0]

    last_log = _latest_webhook_delivery_log()
    assert last_log is not None
    assert last_log["event_type"] == "oic_alert"
    assert last_log["severity"] == "critical"
    assert last_log["status"] == "failed"
    assert last_log["attempts"] == 3


def test_webhook_adapter_payload_minimal_contract(monkeypatch) -> None:
    # Feature: payload should remain minimal JSON contract: event/severity/timestamp/integration
    settings_repo = SettingsRepository()
    adapter = WebhookAdapter(settings_repo)

    settings_repo.upsert_settings(
        type("Payload", (), {
            "oic_base_url": "https://oic.local",
            "auth_mode": "OAuth2",
            "polling_seconds": 30,
            "notification_email": "ops@example.com",
            "threshold_issue_score_warning": 12,
            "threshold_issue_score_critical": 18,
            "threshold_missed_schedules_warning": 3,
            "threshold_missed_schedules_critical": 5,
            "threshold_critical_integrations_warning": 20,
            "threshold_critical_integrations_critical": 35,
            "webhook_enabled": True,
            "webhook_url": "https://example.com/hook",
            "webhook_bearer_token": "token-minimal",
            "webhook_max_retries": 3,
            "webhook_initial_backoff_seconds": 0.5,
            "webhook_timeout_seconds": 3,
        })()
    )

    captured_payload: dict = {}

    class _Resp:
        status_code = 200

    def _capture_post(url, json, headers, timeout):
        captured_payload.update(json)
        return _Resp()

    monkeypatch.setattr("app.services.webhook_adapter.requests.post", _capture_post)
    monkeypatch.setattr("app.services.webhook_adapter.time.sleep", lambda *_: None)

    adapter.send_alert_event(
        severity="warning",
        integration_id="INTG-010",
        alert_title="Collector generated warning",
        event_time_iso="2026-02-15T13:00:00+00:00",
    )

    assert set(captured_payload.keys()) == {"event", "severity", "timestamp", "integration_id"}


def test_collector_alert_webhook_invocation_logic_for_warning_and_critical() -> None:
    # Feature: collector webhook invocation path dispatches warning/critical events to adapter
    calls: list[dict] = []

    class DummyAdapter:
        def send_alert_event(self, **kwargs):
            calls.append(kwargs)

    class SyncThread:
        def __init__(self, target, kwargs, daemon):
            self._target = target
            self._kwargs = kwargs

        def start(self):
            self._target(**self._kwargs)

    original_thread = __import__("app.repositories.collector_repository", fromlist=["threading"]).threading.Thread
    try:
        __import__("app.repositories.collector_repository", fromlist=["threading"]).threading.Thread = SyncThread
        collector = CollectorRepository(webhook_adapter=DummyAdapter())
        collector._send_webhook(
            severity="warning",
            integration_id="INTG-123",
            title="warning",
            event_time_iso="2026-02-15T14:00:00+00:00",
            inserted_id=1,
        )
        collector._send_webhook(
            severity="critical",
            integration_id="INTG-124",
            title="critical",
            event_time_iso="2026-02-15T14:00:00+00:00",
            inserted_id=2,
        )
    finally:
        __import__("app.repositories.collector_repository", fromlist=["threading"]).threading.Thread = original_thread

    assert len(calls) == 2
    assert calls[0]["severity"] == "warning"
    assert calls[1]["severity"] == "critical"


def test_manual_collector_run_triggers_webhook_delivery_attempt_logs(
    api_client: requests.Session, admin_token: str
) -> None:
    # Feature: collector-triggered warning/critical alerts invoke webhook adapter delivery attempts
    headers = {"Authorization": f"Bearer {admin_token}"}
    before_settings = api_client.get(f"{BASE_URL}/api/settings", headers=headers, timeout=20)
    assert before_settings.status_code == 200
    original = before_settings.json()

    before_count = _webhook_log_count()
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
            "webhook_bearer_token": "collector-token",
        }
        update_response = api_client.put(f"{BASE_URL}/api/settings", json=update_payload, headers=headers, timeout=20)
        assert update_response.status_code == 200

        run_response = api_client.post(f"{BASE_URL}/api/mock-collector/run", headers=headers, timeout=40)
        assert run_response.status_code == 200
        assert run_response.json()["updated_integrations"] >= 25

        time.sleep(3)
        after_count = _webhook_log_count()
        assert after_count > before_count

        last_log = _latest_webhook_delivery_log()
        assert last_log is not None
        assert last_log["severity"] in {"warning", "critical"}
    finally:
        restore = api_client.put(f"{BASE_URL}/api/settings", json=original, headers=headers, timeout=20)
        assert restore.status_code == 200
