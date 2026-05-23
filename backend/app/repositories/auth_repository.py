from __future__ import annotations

import hashlib
import os
import re
import secrets
import string
import uuid
from datetime import datetime, timedelta, timezone

from app.database import get_connection
from app.services.auth_service import hash_password, verify_password


class AuthRepository:
    MAX_FAILED_ATTEMPTS = 5
    LOCKOUT_MINUTES = 15

    def has_admin_user(self) -> bool:
        with get_connection() as connection:
            count = connection.execute("SELECT COUNT(*) FROM admin_users").fetchone()[0]
        return count > 0

    def create_first_admin(self, *, email: str, password: str) -> str:
        if self.has_admin_user():
            raise ValueError("Admin already exists")

        self._validate_password_strength(password)
        password_hash, salt = hash_password(password)
        normalized_email = email.lower().strip()

        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO admin_users (email, password_hash, salt, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (normalized_email, password_hash, salt, datetime.now(timezone.utc).isoformat()),
            )
            connection.commit()

        return normalized_email

    def verify_admin_credentials(self, *, email: str, password: str) -> tuple[bool, str]:
        normalized_email = email.lower().strip()
        now = datetime.now(timezone.utc)

        with get_connection() as connection:
            lock_row = connection.execute(
                "SELECT failed_count, locked_until FROM admin_login_security WHERE email = ?",
                (normalized_email,),
            ).fetchone()

            if lock_row and lock_row["locked_until"]:
                locked_until = datetime.fromisoformat(lock_row["locked_until"])
                if locked_until > now:
                    return False, "Account temporarily locked after repeated failed attempts"

            user_row = connection.execute(
                "SELECT password_hash, salt FROM admin_users WHERE email = ?",
                (normalized_email,),
            ).fetchone()

            if user_row and verify_password(password, user_row["password_hash"], user_row["salt"]):
                connection.execute(
                    """
                    INSERT OR REPLACE INTO admin_login_security (email, failed_count, locked_until, updated_at)
                    VALUES (?, 0, NULL, ?)
                    """,
                    (normalized_email, now.isoformat()),
                )
                connection.commit()
                return True, "ok"

            failed_count = 1
            if lock_row:
                failed_count = int(lock_row["failed_count"] or 0) + 1

            locked_until_iso = None
            message = "Invalid admin credentials"
            if failed_count >= self.MAX_FAILED_ATTEMPTS:
                locked_until_iso = (now + timedelta(minutes=self.LOCKOUT_MINUTES)).isoformat()
                failed_count = 0
                message = "Account temporarily locked after repeated failed attempts"

            connection.execute(
                """
                INSERT OR REPLACE INTO admin_login_security (email, failed_count, locked_until, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (normalized_email, failed_count, locked_until_iso, now.isoformat()),
            )
            connection.commit()

        return False, message

    def create_session(self, *, email: str, revoke_previous: bool = True) -> tuple[str, str]:
        normalized_email = email.lower().strip()
        now = datetime.now(timezone.utc)
        ttl_seconds = int(os.environ["ADMIN_TOKEN_TTL_SECONDS"])
        expires_at = (now + timedelta(seconds=ttl_seconds)).isoformat()
        session_id = str(uuid.uuid4())

        with get_connection() as connection:
            if revoke_previous:
                connection.execute(
                    """
                    UPDATE admin_sessions
                    SET revoked_at = ?, revoke_reason = ?
                    WHERE email = ? AND revoked_at IS NULL
                    """,
                    (now.isoformat(), "auto_revoke_on_new_login", normalized_email),
                )

            connection.execute(
                """
                INSERT INTO admin_sessions (session_id, email, issued_at, expires_at, revoked_at, revoke_reason)
                VALUES (?, ?, ?, ?, NULL, NULL)
                """,
                (session_id, normalized_email, now.isoformat(), expires_at),
            )
            connection.commit()

        return session_id, expires_at

    def revoke_all_sessions(self, *, email: str, reason: str) -> int:
        normalized_email = email.lower().strip()
        now = datetime.now(timezone.utc).isoformat()
        with get_connection() as connection:
            cursor = connection.execute(
                """
                UPDATE admin_sessions
                SET revoked_at = ?, revoke_reason = ?
                WHERE email = ? AND revoked_at IS NULL
                """,
                (now, reason, normalized_email),
            )
            connection.commit()
        return int(cursor.rowcount or 0)

    def is_session_active(self, *, email: str, session_id: str) -> bool:
        normalized_email = email.lower().strip()
        now_iso = datetime.now(timezone.utc).isoformat()
        with get_connection() as connection:
            row = connection.execute(
                """
                SELECT session_id
                FROM admin_sessions
                WHERE session_id = ?
                  AND email = ?
                  AND revoked_at IS NULL
                  AND expires_at > ?
                """,
                (session_id, normalized_email, now_iso),
            ).fetchone()
        return row is not None

    def create_password_reset_code(self, *, email: str, expiry_minutes: int = 60) -> str:
        normalized_email = email.lower().strip()
        now = datetime.now(timezone.utc)

        with get_connection() as connection:
            user_row = connection.execute(
                "SELECT email FROM admin_users WHERE email = ?",
                (normalized_email,),
            ).fetchone()
            if user_row is None:
                raise ValueError("No admin account found for this email")

            reset_code = "".join(secrets.choice(string.digits) for _ in range(8))
            code_hash = self._hash_reset_code(normalized_email, reset_code)
            expires_at = (now + timedelta(minutes=expiry_minutes)).isoformat()

            connection.execute(
                """
                INSERT INTO password_reset_codes (email, code_hash, expires_at, used_at, created_at)
                VALUES (?, ?, ?, NULL, ?)
                """,
                (normalized_email, code_hash, expires_at, now.isoformat()),
            )
            connection.commit()

        return reset_code

    def reset_password_with_code(self, *, email: str, reset_code: str, new_password: str) -> tuple[bool, str]:
        normalized_email = email.lower().strip()
        self._validate_password_strength(new_password)
        now = datetime.now(timezone.utc)

        with get_connection() as connection:
            row = connection.execute(
                """
                SELECT id, code_hash, expires_at
                FROM password_reset_codes
                WHERE email = ? AND used_at IS NULL
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (normalized_email,),
            ).fetchone()

            if row is None:
                return False, "No active reset code found"

            if datetime.fromisoformat(row["expires_at"]) <= now:
                return False, "Reset code has expired"

            expected_hash = self._hash_reset_code(normalized_email, reset_code)
            if expected_hash != row["code_hash"]:
                return False, "Invalid reset code"

            password_hash, salt = hash_password(new_password)
            connection.execute(
                "UPDATE admin_users SET password_hash = ?, salt = ? WHERE email = ?",
                (password_hash, salt, normalized_email),
            )
            connection.execute(
                "UPDATE password_reset_codes SET used_at = ? WHERE id = ?",
                (now.isoformat(), row["id"]),
            )
            connection.execute(
                """
                UPDATE admin_sessions
                SET revoked_at = ?, revoke_reason = ?
                WHERE email = ? AND revoked_at IS NULL
                """,
                (now.isoformat(), "password_reset", normalized_email),
            )
            connection.commit()

        return True, "Password reset successful"

    @staticmethod
    def _hash_reset_code(email: str, reset_code: str) -> str:
        secret = os.environ["ADMIN_AUTH_SECRET"]
        raw = f"{email}|{reset_code}|{secret}".encode()
        return hashlib.sha256(raw).hexdigest()

    @staticmethod
    def _validate_password_strength(password: str) -> None:
        if len(password) < 10:
            raise ValueError("Password must be at least 10 characters long")
        checks = [
            re.search(r"[a-z]", password),
            re.search(r"[A-Z]", password),
            re.search(r"\d", password),
            re.search(r"[^A-Za-z0-9]", password),
        ]
        if not all(checks):
            raise ValueError(
                "Password must include uppercase, lowercase, number, and special character"
            )
