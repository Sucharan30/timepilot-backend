"""
backend/repositories/session_repository.py

Data-access layer for the sessions table.
Manages refresh-token persistence and lookup for logout / token rotation.
"""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session as DBSession

from backend.models.session import UserSession


class SessionRepository:

    @staticmethod
    def create_session(
        db: DBSession,
        user_id: int,
        refresh_token: str,
        expires_at: datetime,
    ) -> UserSession:
        """Persist a new refresh-token session row."""
        session = UserSession(
            user_id=user_id,
            refresh_token=refresh_token,
            expires_at=expires_at,
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        return session

    @staticmethod
    def get_by_token(db: DBSession, refresh_token: str) -> Optional[UserSession]:
        """Look up a session by its refresh token string."""
        return (
            db.query(UserSession)
            .filter(UserSession.refresh_token == refresh_token)
            .first()
        )

    @staticmethod
    def delete_session(db: DBSession, refresh_token: str) -> bool:
        """
        Delete a session by refresh token (logout).
        Returns True if a row was deleted, False if not found.
        """
        session = SessionRepository.get_by_token(db, refresh_token)
        if session:
            db.delete(session)
            db.commit()
            return True
        return False

    @staticmethod
    def delete_all_for_user(db: DBSession, user_id: int) -> int:
        """Delete all sessions for a user (force logout everywhere)."""
        deleted = (
            db.query(UserSession)
            .filter(UserSession.user_id == user_id)
            .delete(synchronize_session=False)
        )
        db.commit()
        return deleted

    @staticmethod
    def is_token_valid(session: UserSession) -> bool:
        """Check that a session's refresh token has not expired."""
        now = datetime.now(timezone.utc)
        # Make expires_at offset-aware for comparison
        exp = session.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        return exp > now
