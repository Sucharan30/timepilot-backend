"""
backend/repositories/user_repository.py

Data-access layer for the users table.
All DB queries for User go through here — keeps services DB-agnostic.
"""
from typing import Optional

from sqlalchemy.orm import Session

from backend.models.user import User


class UserRepository:

    @staticmethod
    def get_by_phone(db: Session, phone_number: str) -> Optional[User]:
        """Fetch a user by their phone number."""
        return db.query(User).filter(User.phone_number == phone_number).first()

    @staticmethod
    def get_by_id(db: Session, user_id: int) -> Optional[User]:
        """Fetch a user by primary key."""
        return db.query(User).filter(User.id == user_id).first()

    @staticmethod
    def create(db: Session, phone_number: str, full_name: Optional[str] = None) -> User:
        """Create a new user and persist to DB."""
        user = User(phone_number=phone_number, full_name=full_name)
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def get_or_create(db: Session, phone_number: str) -> tuple[User, bool]:
        """
        Returns (user, created).
        If user exists, returns it with created=False.
        If not, creates one and returns created=True.
        """
        user = UserRepository.get_by_phone(db, phone_number)
        if user:
            return user, False
        user = UserRepository.create(db, phone_number)
        return user, True

    @staticmethod
    def mark_verified(db: Session, user: User) -> User:
        """Mark a user's phone as verified."""
        user.is_verified = True
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def update_name(db: Session, user: User, full_name: str) -> User:
        """Update the user's display name."""
        user.full_name = full_name
        db.commit()
        db.refresh(user)
        return user
