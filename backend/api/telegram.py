"""
backend/api/telegram.py

Telegram Bot webhook endpoint.
  POST /telegram/webhook

Telegram calls this URL with an Update JSON payload whenever a user
messages the bot.  This route hands off to the TelegramProvider which
handles the logic.

Day-2 behaviour: echo "Hello, I am TimePilot AI." for any message.

Setup (run once after deploying to Railway):
  https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/setWebhook?url=<RAILWAY_URL>/telegram/webhook
"""
from typing import Any

from fastapi import APIRouter, Request

from backend.providers.telegram.telegram_provider import TelegramProvider
from backend.schemas.response import ok

router = APIRouter(prefix="/telegram", tags=["Telegram"])

_telegram = TelegramProvider()


@router.post("/webhook")
async def telegram_webhook(request: Request):
    """
    Receives raw Telegram Update payloads and delegates to TelegramProvider.
    Always returns 200 OK immediately (Telegram re-tries on non-200).
    """
    try:
        update: dict[str, Any] = await request.json()
        _telegram.handle_update(update)
    except Exception as exc:
        # Never return a non-200 to Telegram — it will spam retries
        print(f"[telegram_webhook] Error handling update: {exc}")

    return ok({"received": True})
