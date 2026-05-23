"""Regression tests for cookie sessions, CSRF, bearer compatibility, and auth hardening."""

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
    # Module: shared HTTP session for cookie and bearer auth checks
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture()
def admin_credentials() -> tuple[str, str]:
    return _get_admin_credentials()


def _login_cookie_session(api_client: requests.Session, admin_credentials: tuple[str, str]) -> dict:
    email, password = admin_credentials
    response = api_client.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": password},
        timeout=20,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["email"] == email
    assert isinstance(payload["token"], str)
    assert len(payload["token"]) > 20
    return payload


def test_login_sets_session_and_csrf_cookies(
    api_client: requests.Session, admin_credentials: tuple[str, str]
) -> None:
    # Feature: login issues cookie session + csrf token cookies
    _login_cookie_session(api_client, admin_credentials)

    cookie_names = {cookie.name for cookie in api_client.cookies}
    assert "session_token" in cookie_names
    assert "csrf_token" in cookie_names


def test_cookie_auth_status_reports_authenticated_email(
    api_client: requests.Session, admin_credentials: tuple[str, str]
) -> None:
    # Feature: auth/status resolves actor from session cookie without bearer header
    email, _ = admin_credentials
    _login_cookie_session(api_client, admin_credentials)

    response = api_client.get(f"{BASE_URL}/api/auth/status", timeout=20)
    assert response.status_code == 200
    payload = response.json()
    assert payload["has_admin"] is True
    assert payload["authenticated_email"] == email


def test_cookie_state_change_requires_csrf_header(
    api_client: requests.Session, admin_credentials: tuple[str, str]
) -> None:
    # Feature: cookie-authenticated state-changing endpoints enforce CSRF validation
    _login_cookie_session(api_client, admin_credentials)

    get_settings = api_client.get(f"{BASE_URL}/api/settings", timeout=20)
    assert get_settings.status_code == 200
    existing = get_settings.json()

    update_payload = {
        **existing,
        "oic_base_url": "https://csrf-check.example.com",
    }

    no_csrf_resp = api_client.put(f"{BASE_URL}/api/settings", json=update_payload, timeout=20)
    assert no_csrf_resp.status_code == 403

    csrf_value = next((cookie.value for cookie in api_client.cookies if cookie.name == "csrf_token"), None)
    assert csrf_value

    with_csrf_resp = api_client.put(
        f"{BASE_URL}/api/settings",
        json=update_payload,
        headers={"X-CSRF-Token": csrf_value},
        timeout=20,
    )
    assert with_csrf_resp.status_code == 200
    persisted = with_csrf_resp.json()
    assert persisted["oic_base_url"] == update_payload["oic_base_url"]

    restore_resp = api_client.put(
        f"{BASE_URL}/api/settings",
        json=existing,
        headers={"X-CSRF-Token": csrf_value},
        timeout=20,
    )
    assert restore_resp.status_code == 200


def test_cookie_manual_collector_requires_csrf_header(
    api_client: requests.Session, admin_credentials: tuple[str, str]
) -> None:
    # Feature: manual collector trigger requires CSRF for cookie auth
    _login_cookie_session(api_client, admin_credentials)

    no_csrf_resp = api_client.post(f"{BASE_URL}/api/mock-collector/run", timeout=30)
    assert no_csrf_resp.status_code == 403

    csrf_value = next((cookie.value for cookie in api_client.cookies if cookie.name == "csrf_token"), None)
    assert csrf_value
    with_csrf_resp = api_client.post(
        f"{BASE_URL}/api/mock-collector/run",
        headers={"X-CSRF-Token": csrf_value},
        timeout=30,
    )
    assert with_csrf_resp.status_code == 200
    payload = with_csrf_resp.json()
    assert isinstance(payload["updated_integrations"], int)
    assert payload["updated_integrations"] >= 25


def test_bearer_auth_still_works_for_protected_flows(
    api_client: requests.Session, admin_credentials: tuple[str, str]
) -> None:
    # Feature: bearer token remains valid for automated test compatibility
    token = _login_cookie_session(api_client, admin_credentials)["token"]
    headers = {"Authorization": f"Bearer {token}"}

    get_resp = api_client.get(f"{BASE_URL}/api/settings", headers=headers, timeout=20)
    assert get_resp.status_code == 200
    values = get_resp.json()
    assert "oic_base_url" in values

    put_resp = api_client.put(f"{BASE_URL}/api/settings", headers=headers, json=values, timeout=20)
    assert put_resp.status_code == 200


def test_logout_clears_cookie_session(api_client: requests.Session, admin_credentials: tuple[str, str]) -> None:
    # Feature: logout invalidates session cookie auth
    _login_cookie_session(api_client, admin_credentials)

    logout_resp = api_client.post(f"{BASE_URL}/api/auth/logout", timeout=20)
    assert logout_resp.status_code == 200
    assert logout_resp.json()["status"] == "logged_out"

    post_logout = api_client.get(f"{BASE_URL}/api/settings", timeout=20)
    assert post_logout.status_code == 401


def test_lockout_after_repeated_failed_attempts(api_client: requests.Session) -> None:
    # Feature: login lockout after repeated failed attempts
    lockout_email = "lockout-test@badger.local"

    statuses: list[int] = []
    for _ in range(5):
        response = api_client.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": lockout_email, "password": "WrongPass999!"},
            timeout=20,
        )
        statuses.append(response.status_code)

    assert statuses[0] == 401
    assert statuses[-1] == 423


def test_register_admin_complexity_enforced_when_first_admin_absent(api_client: requests.Session) -> None:
    # Feature: first-admin route rejects weak password when registration path is active
    status_response = api_client.get(f"{BASE_URL}/api/auth/status", timeout=20)
    assert status_response.status_code == 200
    status_payload = status_response.json()

    if status_payload["has_admin"]:
        pytest.skip("Admin already exists in shared environment; first-admin complexity path not reachable")

    weak_response = api_client.post(
        f"{BASE_URL}/api/auth/register-admin",
        json={"email": "weak-admin@badger.local", "password": "weakpass"},
        timeout=20,
    )
    assert weak_response.status_code == 400
    detail = weak_response.json().get("detail", "")
    assert "Password" in detail
