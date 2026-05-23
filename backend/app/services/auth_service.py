from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")


def hash_password(password: str, salt_hex: str | None = None) -> tuple[str, str]:
    salt = bytes.fromhex(salt_hex) if salt_hex else secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 120_000)
    return digest.hex(), salt.hex()


def verify_password(password: str, expected_hash: str, salt_hex: str) -> bool:
    computed_hash, _ = hash_password(password, salt_hex)
    return hmac.compare_digest(computed_hash, expected_hash)


def create_token(email: str, session_id: str) -> str:
    secret = os.environ["ADMIN_AUTH_SECRET"].encode()
    ttl_seconds = int(os.environ["ADMIN_TOKEN_TTL_SECONDS"])
    payload = {
        "sub": email,
        "sid": session_id,
        "exp": int(time.time()) + ttl_seconds,
    }
    payload_raw = json.dumps(payload, separators=(",", ":")).encode()
    payload_encoded = base64.urlsafe_b64encode(payload_raw).decode().rstrip("=")
    signature = hmac.new(secret, payload_encoded.encode(), hashlib.sha256).hexdigest()
    return f"{payload_encoded}.{signature}"


def validate_token_data(token: str) -> dict:
    if "." not in token:
        raise ValueError("Malformed token")

    payload_encoded, signature = token.split(".", 1)
    secret = os.environ["ADMIN_AUTH_SECRET"].encode()
    expected = hmac.new(secret, payload_encoded.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise ValueError("Invalid token signature")

    padding = "=" * (-len(payload_encoded) % 4)
    payload_raw = base64.urlsafe_b64decode(f"{payload_encoded}{padding}".encode())
    payload = json.loads(payload_raw.decode())

    if int(payload["exp"]) < int(time.time()):
        raise ValueError("Token expired")

    return payload


def validate_token(token: str) -> str:
    payload = validate_token_data(token)
    return str(payload["sub"])
