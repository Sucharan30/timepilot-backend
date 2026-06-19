"""
backend/services/jwt_service.py

Stateless JWT operations:
  - create_access_token   → short-lived token (sub = user_id, type = "access")
  - create_refresh_token  → long-lived token (sub = user_id, type = "refresh")
  - decode_token          → verifies signature + expiry, returns payload dict

All secrets and expiry windows come from Settings (env vars).
"""
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import jwt, JWTError

from backend.core.config import get_settings

settings = get_settings()


class JWTService:

    @staticmethod
    def create_access_token(user_id: int) -> str:
        """Create a short-lived access token."""
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )
        payload: dict[str, Any] = {
            "sub": str(user_id),
            "type": "access",
            "exp": expire,
            "iat": datetime.now(timezone.utc),
        }
        return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)

    @staticmethod
    def create_refresh_token(user_id: int) -> tuple[str, datetime]:
        """
        Create a long-lived refresh token.
        Returns (token_string, expires_at_datetime) so the caller can
        persist the expiry in the sessions table.
        """
        expire = datetime.now(timezone.utc) + timedelta(
            days=settings.REFRESH_TOKEN_EXPIRE_DAYS
        )
        payload: dict[str, Any] = {
            "sub": str(user_id),
            "type": "refresh",
            "exp": expire,
            "iat": datetime.now(timezone.utc),
        }
        token = jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
        return token, expire

    @staticmethod
    def decode_token(token: str) -> dict[str, Any]:
        """
        Decode and verify a JWT.
        Raises jose.JWTError on invalid signature, expired, or malformed token.
        """
        try:
            payload = jwt.decode(
                token,
                settings.JWT_SECRET,
                algorithms=[settings.JWT_ALGORITHM],
            )
            return payload
        except JWTError as exc:
            raise exc
