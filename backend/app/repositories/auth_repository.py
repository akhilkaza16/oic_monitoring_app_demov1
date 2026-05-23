from __future__ import annotations

import re
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
