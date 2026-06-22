"""
backend/scheduler/scheduler.py

APScheduler-based background task runner.

Jobs:
  1. Every minute  — check notifications table, send Telegram reminders for due items
  2. Every day 7AM — send daily briefing via Telegram

Setup: call start_scheduler() once at app startup (in main.py lifespan).
"""
import json
import re
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from backend.database import SessionLocal


# ── Internal helpers ──────────────────────────────────────────────────────────

def _get_telegram_provider():
    from backend.providers.telegram.telegram_provider import TelegramProvider
    return TelegramProvider()


def _get_settings():
    from backend.core.config import get_settings
    return get_settings()


# ── Job 1: Notification Checker (every minute) ────────────────────────────────

def check_notifications():
    """
    Queries the notifications table for any unsent notifications
    whose notification_time has passed. Sends Telegram message and marks as sent.
    """
    db = SessionLocal()
    try:
        from backend.models.notification import Notification
        from backend.models.event import Event

        now = datetime.now(timezone.utc)
        due = (
            db.query(Notification)
            .filter(
                Notification.sent == False,           # noqa: E712
                Notification.notification_time <= now,
            )
            .all()
        )

        if not due:
            return

        telegram = _get_telegram_provider()

        for notif in due:
            # Get the event title
            event = db.query(Event).filter(Event.id == notif.event_id).first()
            if not event:
                continue

            # Get the user's Telegram chat_id
            from backend.models.telegram_account import TelegramAccount
            tg = db.query(TelegramAccount).filter(TelegramAccount.user_id == notif.user_id).first()
            if not tg or not tg.telegram_chat_id:
                continue

            message = f"⏰ *Reminder*\n\n*{event.title}* starts now.\n\nStay on schedule! 🚀"
            sent = telegram.send_message(tg.telegram_chat_id, message)

            if sent:
                notif.sent = True
                db.commit()

    except Exception as exc:
        print(f"[Scheduler] check_notifications error: {exc}")
    finally:
        db.close()


# ── Job 2: Daily Briefing (every day at 7:00 AM UTC) ─────────────────────────

def send_daily_briefing():
    """
    Sends a daily briefing to every user who has a linked Telegram account.
    Uses Gemini to generate a short summary of the day.
    """
    db = SessionLocal()
    try:
        from backend.models.telegram_account import TelegramAccount
        from backend.models.user import User

        settings = _get_settings()
        telegram = _get_telegram_provider()

        # All users with connected Telegram accounts
        linked_accounts = db.query(TelegramAccount).filter(
            TelegramAccount.is_connected == True,  # noqa: E712
            TelegramAccount.telegram_chat_id.isnot(None),
        ).all()

        for account in linked_accounts:
            try:
                _send_briefing_for_user(db, account, telegram, settings)
            except Exception as exc:
                print(f"[Scheduler] briefing error for user {account.user_id}: {exc}")

    except Exception as exc:
        print(f"[Scheduler] send_daily_briefing error: {exc}")
    finally:
        db.close()


def _send_briefing_for_user(db, account, telegram, settings):
    from backend.models.event import Event, EventStatus
    from decimal import Decimal
    from backend.repositories.expense_repository import ExpenseRepository
    from backend.repositories.analytics_repository import StreakRepository

    now       = datetime.now(timezone.utc)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end   = now.replace(hour=23, minute=59, second=59)

    # Today's events
    today_events = (
        db.query(Event)
        .filter(
            Event.user_id == account.user_id,
            Event.start_datetime >= day_start,
            Event.start_datetime <= day_end,
            Event.status == EventStatus.scheduled,
        )
        .order_by(Event.start_datetime.asc())
        .all()
    )

    # Today's spending
    todays_expenses = ExpenseRepository.get_for_period(db, account.user_id, day_start, day_end)
    daily_spend = sum(float(e.amount) for e in todays_expenses)

    # Streak
    prod_streak = StreakRepository.get_or_create(db, account.user_id, "productivity")

    # Build message
    schedule_lines = "\n".join(
        [f"  • {e.start_datetime.strftime('%I:%M %p')} — {e.title}" for e in today_events]
    ) or "  No events scheduled for today."

    message = (
        f"☀️ *Good Morning!*\n\n"
        f"📅 *Today's Schedule*\n{schedule_lines}\n\n"
        f"💰 *Budget Today*: ₹{daily_spend:.2f} spent\n\n"
        f"🔥 *Productivity Streak*: {prod_streak.current_count} day(s)\n\n"
        f"Have a productive day! 💪"
    )

    telegram.send_message(account.telegram_chat_id, message)


# ── Scheduler setup ───────────────────────────────────────────────────────────

_scheduler: BackgroundScheduler | None = None


def start_scheduler():
    """Call once at app startup."""
    global _scheduler
    if _scheduler and _scheduler.running:
        return

    _scheduler = BackgroundScheduler(timezone="UTC")

    # Check notifications every minute
    _scheduler.add_job(
        check_notifications,
        trigger=IntervalTrigger(minutes=1),
        id="notification_checker",
        replace_existing=True,
        misfire_grace_time=30,
    )

    # Daily briefing at 7:00 AM UTC
    _scheduler.add_job(
        send_daily_briefing,
        trigger=CronTrigger(hour=7, minute=0),
        id="daily_briefing",
        replace_existing=True,
        misfire_grace_time=300,
    )

    _scheduler.start()
    print("[Scheduler] Started — notification checker (1 min) + daily briefing (7 AM UTC)")


def stop_scheduler():
    """Call at app shutdown."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        print("[Scheduler] Stopped.")
