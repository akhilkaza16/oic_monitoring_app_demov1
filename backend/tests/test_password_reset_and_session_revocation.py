"""Regression tests for password reset, session revocation, and auth compatibility."""

from __future__ import annotations

import os
import secrets
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


def _load_test_credentials() -> tuple[str, str]:
    # Module: credential source of truth for auth flow testing
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


def _generate_temp_password() -> str:
    return f"Tmp!{secrets.token_hex(6)}Aa1"


@pytest.fixture()
def api_client() -> requests.Session:
    # Module: shared HTTP session for cookie + bearer compatibility checks
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


def _login_and_get_token(client: requests.Session, email: str, password: str) -> str:
    response = client.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": password},
        timeout=20,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["email"] == email
    assert isinstance(payload["token"], str)
    assert len(payload["token"]) > 20
    return payload["token"]


def _extract_csrf_cookie(client: requests.Session) -> str:
    csrf_token = next((cookie.value for cookie in client.cookies if cookie.name == "csrf_token"), None)
    assert csrf_token
    return csrf_token


def test_password_reset_request_returns_code_and_60_min_expiry(api_client: requests.Session) -> None:
    # Feature: request endpoint returns one-time code with 60-minute expiry metadata
    response = api_client.post(
        f"{BASE_URL}/api/auth/password-reset/request",
        json={"email": ADMIN_EMAIL},
        timeout=20,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "code_generated"
    assert payload["expires_in_minutes"] == 60
    assert isinstance(payload["reset_code"], str)
    assert payload["reset_code"].isdigit()
    assert len(payload["reset_code"]) == 8


def test_password_reset_confirm_updates_password_revokes_sessions_and_blocks_reuse(
    api_client: requests.Session,
) -> None:
    # Feature: reset confirm validates code, changes password, revokes active sessions, and marks code used
    old_password = ADMIN_PASSWORD
    temp_password = _generate_temp_password()

    first_token = _login_and_get_token(api_client, ADMIN_EMAIL, old_password)

    reset_request = api_client.post(
        f"{BASE_URL}/api/auth/password-reset/request",
        json={"email": ADMIN_EMAIL},
        timeout=20,
    )
    assert reset_request.status_code == 200
    reset_payload = reset_request.json()
    reset_code = reset_payload["reset_code"]

    confirm_response = api_client.post(
        f"{BASE_URL}/api/auth/password-reset/confirm",
        json={"email": ADMIN_EMAIL, "reset_code": reset_code, "new_password": temp_password},
        timeout=20,
    )
    assert confirm_response.status_code == 200
    assert confirm_response.json()["status"] == "password_reset_completed"

    old_session_rejected = api_client.get(
        f"{BASE_URL}/api/settings",
        headers={"Authorization": f"Bearer {first_token}"},
        timeout=20,
    )
    assert old_session_rejected.status_code == 401
    assert "revoked" in old_session_rejected.json()["detail"].lower()

    login_with_old_password = api_client.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": old_password},
        timeout=20,
    )
    assert login_with_old_password.status_code == 401

    login_with_new_password = api_client.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": temp_password},
        timeout=20,
    )
    assert login_with_new_password.status_code == 200
    new_token = login_with_new_password.json()["token"]

    restore_response = api_client.post(
        f"{BASE_URL}/api/auth/password-reset/request",
        json={"email": ADMIN_EMAIL},
        timeout=20,
    )
    assert restore_response.status_code == 200
    restore_code = restore_response.json()["reset_code"]

    restore_confirm = api_client.post(
        f"{BASE_URL}/api/auth/password-reset/confirm",
        json={"email": ADMIN_EMAIL, "reset_code": restore_code, "new_password": old_password},
        timeout=20,
    )
    assert restore_confirm.status_code == 200

    reused_code = api_client.post(
        f"{BASE_URL}/api/auth/password-reset/confirm",
        json={"email": ADMIN_EMAIL, "reset_code": restore_code, "new_password": temp_password},
        timeout=20,
    )
    assert reused_code.status_code == 400
    detail = reused_code.json()["detail"]
    assert detail in {"No active reset code found", "Invalid reset code"}

    new_token_rejected = api_client.get(
        f"{BASE_URL}/api/settings",
        headers={"Authorization": f"Bearer {new_token}"},
        timeout=20,
    )
    assert new_token_rejected.status_code == 401


def test_auto_revoke_previous_sessions_on_new_login(api_client: requests.Session) -> None:
    # Feature: every new successful login auto-revokes previous active sessions
    first_session_token = _login_and_get_token(api_client, ADMIN_EMAIL, ADMIN_PASSWORD)

    second_login = api_client.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=20,
    )
    assert second_login.status_code == 200
    second_token = second_login.json()["token"]

    first_token_response = api_client.get(
        f"{BASE_URL}/api/settings",
        headers={"Authorization": f"Bearer {first_session_token}"},
        timeout=20,
    )
    assert first_token_response.status_code == 401
    assert "revoked" in first_token_response.json()["detail"].lower()

    second_token_response = api_client.get(
        f"{BASE_URL}/api/settings",
        headers={"Authorization": f"Bearer {second_token}"},
        timeout=20,
    )
    assert second_token_response.status_code == 200
    assert "oic_base_url" in second_token_response.json()


def test_manual_revoke_all_sessions_requires_auth_and_csrf_then_revokes_cookie_session(
    api_client: requests.Session,
) -> None:
    # Feature: manual revoke endpoint enforces auth+CSRF and revokes current session
    _login_and_get_token(api_client, ADMIN_EMAIL, ADMIN_PASSWORD)

    no_csrf = api_client.post(f"{BASE_URL}/api/security/revoke-sessions", timeout=20)
    assert no_csrf.status_code == 403

    csrf_token = _extract_csrf_cookie(api_client)
    revoke_response = api_client.post(
        f"{BASE_URL}/api/security/revoke-sessions",
        headers={"X-CSRF-Token": csrf_token},
        timeout=20,
    )
    assert revoke_response.status_code == 200
    payload = revoke_response.json()
    assert isinstance(payload["revoked_sessions"], int)
    assert payload["revoked_sessions"] >= 1

    post_revoke_status = api_client.get(f"{BASE_URL}/api/auth/status", timeout=20)
    assert post_revoke_status.status_code == 200
    assert post_revoke_status.json()["authenticated_email"] is None

    post_revoke_protected = api_client.get(f"{BASE_URL}/api/settings", timeout=20)
    assert post_revoke_protected.status_code == 401


def test_security_page_related_flows_keep_bearer_compatibility_for_write_endpoints(
    api_client: requests.Session,
) -> None:
    # Feature: bearer auth remains usable for protected write endpoints without CSRF header
    token = _login_and_get_token(api_client, ADMIN_EMAIL, ADMIN_PASSWORD)
    headers = {"Authorization": f"Bearer {token}"}

    settings_response = api_client.get(f"{BASE_URL}/api/settings", headers=headers, timeout=20)
    assert settings_response.status_code == 200
    settings_payload = settings_response.json()

    save_response = api_client.put(
        f"{BASE_URL}/api/settings",
        headers=headers,
        json=settings_payload,
        timeout=20,
    )
    assert save_response.status_code == 200
    persisted = save_response.json()
    assert persisted["oic_base_url"] == settings_payload["oic_base_url"]


def test_core_read_flows_and_domain_split_endpoints_no_regression(api_client: requests.Session) -> None:
    # Feature: executive/list/detail/settings-related repositories stay wired after domain split
    summary_response = api_client.get(f"{BASE_URL}/api/executive-summary", timeout=20)
    assert summary_response.status_code == 200
    summary = summary_response.json()
    assert summary["total_integrations"] == 170
    assert len(summary["top_failing_integrations"]) == 5

    list_response = api_client.get(f"{BASE_URL}/api/integrations?limit=10&offset=0", timeout=20)
    assert list_response.status_code == 200
    list_payload = list_response.json()
    assert list_payload["limit"] == 10
    assert len(list_payload["items"]) == 10

    detail_id = list_payload["items"][0]["integration_id"]
    detail_response = api_client.get(f"{BASE_URL}/api/integrations/{detail_id}", timeout=20)
    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload["integration"]["integration_id"] == detail_id

    trends_response = api_client.get(f"{BASE_URL}/api/trends?days=30", timeout=20)
    assert trends_response.status_code == 200
    trends = trends_response.json()
    assert len(trends) == 30

    alerts_response = api_client.get(f"{BASE_URL}/api/alerts?limit=5", timeout=20)
    assert alerts_response.status_code == 200
    assert isinstance(alerts_response.json(), list)
