"""API regression tests for badger-oic-monitor core monitoring features."""

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
ADMIN_EMAIL = "admin@badger.local"
ADMIN_PASSWORD = "BadgerPass123!"


@pytest.fixture()
def api_client() -> requests.Session:
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


def test_health_endpoint(api_client: requests.Session) -> None:
    # Feature: backend startup and basic health availability
    response = api_client.get(f"{BASE_URL}/api/health", timeout=20)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "badger-oic-monitor-backend"


def test_executive_summary_has_seeded_170_and_top_failing(api_client: requests.Session) -> None:
    # Feature: executive summary metrics and top failing integrations
    response = api_client.get(f"{BASE_URL}/api/executive-summary", timeout=20)
    assert response.status_code == 200

    data = response.json()
    assert data["total_integrations"] == 170
    assert isinstance(data["top_failing_integrations"], list)
    assert len(data["top_failing_integrations"]) == 5
    assert 0 <= data["health_score"] <= 100
    assert data["healthy_count"] + data["warning_count"] + data["critical_count"] + data["unknown_count"] == 170


def test_integrations_list_supports_pagination(api_client: requests.Session) -> None:
    # Feature: integrations list pagination contract
    response = api_client.get(f"{BASE_URL}/api/integrations?limit=20&offset=20", timeout=20)
    assert response.status_code == 200

    data = response.json()
    assert data["limit"] == 20
    assert data["offset"] == 20
    assert data["total"] == 170
    assert len(data["items"]) == 20


def test_integrations_list_supports_filters(api_client: requests.Session) -> None:
    # Feature: integrations list filtering by status/project/domain/search
    options_resp = api_client.get(f"{BASE_URL}/api/filter-options", timeout=20)
    assert options_resp.status_code == 200
    options = options_resp.json()
    assert options["projects"]
    assert options["business_domains"]

    project = options["projects"][0]
    domain = options["business_domains"][0]
    filtered_resp = api_client.get(
        f"{BASE_URL}/api/integrations?status=healthy&project={project}&business_domain={domain}&search=INTG-",
        timeout=20,
    )
    assert filtered_resp.status_code == 200
    filtered_data = filtered_resp.json()
    assert filtered_data["total"] >= 0
    for item in filtered_data["items"]:
        assert item["status"] == "healthy"
        assert item["project"] == project
        assert item["business_domain"] == domain
        assert "INTG-" in item["integration_id"]


def test_integration_detail_contains_top_3_recommendations(api_client: requests.Session) -> None:
    # Feature: detail endpoint with deterministic prioritized top-3 recommendations
    summary_resp = api_client.get(f"{BASE_URL}/api/executive-summary", timeout=20)
    assert summary_resp.status_code == 200
    top_id = summary_resp.json()["top_failing_integrations"][0]["integration_id"]

    detail_resp = api_client.get(f"{BASE_URL}/api/integrations/{top_id}", timeout=20)
    assert detail_resp.status_code == 200
    detail = detail_resp.json()

    assert detail["integration"]["integration_id"] == top_id
    assert isinstance(detail["recent_runs"], list)
    assert len(detail["recommendations"]) == 3
    assert [entry["priority"] for entry in detail["recommendations"]] == [1, 2, 3]


def test_latency_logs_capture_middleware_entries(api_client: requests.Session) -> None:
    # Feature: middleware latency logging and retrieval
    for path in ["/api/executive-summary", "/api/integrations?limit=1&offset=0", "/api/auth/status"]:
        resp = api_client.get(f"{BASE_URL}{path}", timeout=20)
        assert resp.status_code == 200

    logs_resp = api_client.get(f"{BASE_URL}/api/latency-logs?limit=10", timeout=20)
    assert logs_resp.status_code == 200
    logs = logs_resp.json()
    assert isinstance(logs, list)
    assert len(logs) > 0
    assert all(entry["latency_ms"] >= 0 for entry in logs)
    assert all(entry["endpoint"].startswith("/api/") for entry in logs)


def test_settings_get_and_put_persist(api_client: requests.Session) -> None:
    # Feature: settings auth + load and save persistence
    status_resp = api_client.get(f"{BASE_URL}/api/auth/status", timeout=20)
    assert status_resp.status_code == 200
    if not status_resp.json()["has_admin"]:
        register_resp = api_client.post(
            f"{BASE_URL}/api/auth/register-admin",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=20,
        )
        assert register_resp.status_code == 200
        token = register_resp.json()["token"]
    else:
        login_resp = api_client.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=20,
        )
        if login_resp.status_code != 200:
            pytest.skip("Skipping settings persistence test: admin credentials unavailable for authenticated flow")
        token = login_resp.json()["token"]

    headers = {"Authorization": f"Bearer {token}"}

    get_resp = api_client.get(f"{BASE_URL}/api/settings", headers=headers, timeout=20)
    assert get_resp.status_code == 200
    before = get_resp.json()

    update_payload = {
        "oic_base_url": "https://qa-oic.example.com",
        "auth_mode": "Basic",
        "polling_seconds": 45,
        "notification_email": "monitoring-team@example.com",
    }
    put_resp = api_client.put(f"{BASE_URL}/api/settings", json=update_payload, headers=headers, timeout=20)
    assert put_resp.status_code == 200
    updated = put_resp.json()
    assert updated["oic_base_url"] == update_payload["oic_base_url"]
    assert updated["auth_mode"] == update_payload["auth_mode"]
    assert updated["polling_seconds"] == update_payload["polling_seconds"]
    assert updated["notification_email"] == update_payload["notification_email"]
    assert "updated_at" in updated

    verify_resp = api_client.get(f"{BASE_URL}/api/settings", headers=headers, timeout=20)
    assert verify_resp.status_code == 200
    after = verify_resp.json()
    assert after["oic_base_url"] == update_payload["oic_base_url"]
    assert after["auth_mode"] == update_payload["auth_mode"]
    assert after["polling_seconds"] == update_payload["polling_seconds"]
    assert after["notification_email"] == update_payload["notification_email"]

    # Restore original settings to keep tests non-invasive
    restore_resp = api_client.put(f"{BASE_URL}/api/settings", json=before, headers=headers, timeout=20)
    assert restore_resp.status_code == 200


def test_mock_collector_run_updates_integrations(api_client: requests.Session) -> None:
    # Feature: mock collector run endpoint updates integrations deterministically
    response = api_client.post(f"{BASE_URL}/api/mock-collector/run", timeout=30)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data["updated_integrations"], int)
    assert data["updated_integrations"] >= 25
