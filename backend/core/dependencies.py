"""
backend/core/dependencies.py

Reusable FastAPI dependencies:
  - get_db       → yields a SQLAlchemy session
  - get_current_user → decodes Bearer JWT and returns the authenticated User
"""
from typing import Generator

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from backend.database import SessionLocal
from backend.services.jwt_service import JWTService
from backend.repositories.user_repository import UserRepository

# ── DB session dependency ─────────────────────────────────────────────────────

def get_db() -> Generator:
    """Yields a SQLAlchemy session and guarantees it is closed after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── JWT auth dependency ───────────────────────────────────────────────────────

_bearer_scheme = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
):
    """
    Validates the Bearer JWT in the Authorization header.
    Returns the authenticated User ORM object, or raises 401.
    """
    token = credentials.credentials

    try:
        payload = JWTService.decode_token(token)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id: int | None = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token payload is malformed.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = UserRepository.get_by_id(db, int(user_id))
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or deactivated.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user
