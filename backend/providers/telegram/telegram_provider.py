"""
backend/providers/telegram/telegram_provider.py

Concrete Telegram provider.
Uses the Bot API (HTTP) via httpx to send messages.

Day-2 behaviour:
  - Any message to the bot receives the reply:
    "Hello, I am TimePilot AI."

Future:
  - Parse commands (/schedule, /list, /cancel)
  - Integrate with SchedulerService
  - Link Telegram chat_id to TimePilot user
"""
import httpx
from typing import Any

from backend.providers.telegram.base import TelegramProviderBase
from backend.core.config import get_settings

settings = get_settings()

# Telegram Bot API base URL
_API_BASE = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}"


class TelegramProvider(TelegramProviderBase):

    def send_message(self, chat_id: str | int, text: str) -> bool:
        """
        Send a text message via Telegram Bot API.
        Returns True on success, logs error and returns False on failure.
        """
        if not settings.TELEGRAM_BOT_TOKEN:
            print("[TelegramProvider] TELEGRAM_BOT_TOKEN is not set. Skipping send.")
            return False

        url = f"{_API_BASE}/sendMessage"
        payload = {"chat_id": chat_id, "text": text}

        try:
            response = httpx.post(url, json=payload, timeout=10)
            response.raise_for_status()
            return True
        except httpx.HTTPError as exc:
            print(f"[TelegramProvider] Failed to send message: {exc}")
            return False

    def handle_update(self, update: dict[str, Any]) -> None:
        """
        Process a Telegram Update dict (received from webhook).

        Day-2: Echo reply to any plain text message.
        """
        message = update.get("message", {})
        if not message:
            # Could be callback_query, inline_query, etc. — ignore for now
            return

        chat_id = message.get("chat", {}).get("id")
        text = message.get("text", "")

        if not chat_id or not text:
            return

        # Day-2 — simple echo greeting
        reply = "Hello, I am TimePilot AI."
        self.send_message(chat_id, reply)
