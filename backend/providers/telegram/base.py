"""
backend/providers/telegram/base.py

Abstract contract for all Telegram provider implementations.
Day-2: TelegramProvider (concrete) handles webhook relay.
Future: Could swap for Pyrogram, Telethon, etc.
"""
from abc import ABC, abstractmethod
from typing import Any


class TelegramProviderBase(ABC):

    @abstractmethod
    def send_message(self, chat_id: str | int, text: str) -> bool:
        """Send a text message to the given Telegram chat/user."""
        ...

    @abstractmethod
    def handle_update(self, update: dict[str, Any]) -> None:
        """
        Process a raw Telegram Update payload received via webhook.
        Implementations decide how to parse and respond.
        """
        ...
