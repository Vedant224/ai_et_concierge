from __future__ import annotations

import os
import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from jose import JWTError, jwt


def hash_password(password: str) -> str:
    iterations = 600_000
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations
    )
    return f"pbkdf2_sha256${iterations}${salt}${digest.hex()}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        algorithm, iteration_text, salt, digest_hex = hashed_password.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(iteration_text)
    except ValueError:
        return False

    candidate = hashlib.pbkdf2_hmac(
        "sha256", plain_password.encode("utf-8"), salt.encode("utf-8"), iterations
    ).hex()
    return hmac.compare_digest(candidate, digest_hex)


def _jwt_secret() -> str:
    return os.getenv("JWT_SECRET", "dev-secret-change-me")


def _jwt_algorithm() -> str:
    return os.getenv("JWT_ALGORITHM", "HS256")


def create_access_token(subject: str) -> str:
    minutes = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
    expire_at = datetime.now(UTC) + timedelta(minutes=minutes)
    payload: dict[str, Any] = {"sub": subject, "type": "access", "exp": expire_at}
    return jwt.encode(payload, _jwt_secret(), algorithm=_jwt_algorithm())


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, _jwt_secret(), algorithms=[_jwt_algorithm()])
        if payload.get("type") != "access":
            raise JWTError("Invalid token type")
        return payload
    except JWTError as exc:
        raise ValueError("Invalid or expired access token") from exc
