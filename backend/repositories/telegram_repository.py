"""
backend/repositories/telegram_repository.py

Data-access layer for TelegramAccount.
All DB queries for TelegramAccount go through here.
"""
from typing import List, Optional

from sqlalchemy.orm import Session

from backend.models.telegram_account import TelegramAccount


class TelegramRepository:

    @staticmethod
    def get_by_chat_id(db: Session, chat_id: str) -> Optional[TelegramAccount]:
        """Fetch TelegramAccount by Telegram chat_id string."""
        return (
            db.query(TelegramAccount)
            .filter(TelegramAccount.telegram_chat_id == str(chat_id))
            .first()
        )

    @staticmethod
    def get_by_user_id(db: Session, user_id: int) -> Optional[TelegramAccount]:
        """Fetch TelegramAccount by user_id."""
        return (
            db.query(TelegramAccount)
            .filter(TelegramAccount.user_id == user_id)
            .first()
        )

    @staticmethod
    def get_or_create_for_user(
        db: Session,
        user_id: int,
        chat_id: str,
        username: Optional[str] = None,
    ) -> TelegramAccount:
        """
        Upsert TelegramAccount for the given user.
        Creates one if it doesn't exist, updates chat_id / username if it does.
        """
        account = db.query(TelegramAccount).filter(
            TelegramAccount.user_id == user_id
        ).first()

        if not account:
            account = TelegramAccount(user_id=user_id)
            db.add(account)

        account.telegram_chat_id  = str(chat_id)
        account.telegram_username = username
        account.is_connected      = True
        db.commit()
        db.refresh(account)
        return account

    @staticmethod
    def get_all_connected(db: Session) -> List[TelegramAccount]:
        """Return all TelegramAccounts that are connected and have a chat_id."""
        return (
            db.query(TelegramAccount)
            .filter(
                TelegramAccount.is_connected == True,       # noqa: E712
                TelegramAccount.telegram_chat_id.isnot(None),
            )
            .all()
        )

    @staticmethod
    def disconnect(db: Session, account: TelegramAccount) -> TelegramAccount:
        """Mark account as disconnected."""
        account.is_connected = False
        db.commit()
        db.refresh(account)
        return account
