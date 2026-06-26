"""
backend/scheduler/scheduler.py

APScheduler-based background task runner.

Jobs:
  1. Every minute  — check notifications table, send Telegram reminders for due items
  2. Every minute  — check each user's configured briefing_time in their local timezone
                     and send daily briefing when their configured time matches

Timezone handling:
  - All comparisons are done against UTC timestamps from DB.
  - User-facing times in messages are converted to the user's local timezone.
  - No hardcoded UTC 7 AM — each user has their own configurable briefing_time.

Setup: call start_scheduler() once at app startup (in main.py lifespan).
"""
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler
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
    whose notification_time has passed.

    Sends a Telegram message formatted as:
      ⏰ Reminder
      Meeting starts in 15 minutes.

    The reminder window is configurable per-user (user.reminder_minutes).
    Marks notification as sent after successful delivery.
    """
    db = SessionLocal()
    try:
        from backend.models.notification import Notification
        from backend.models.event import Event
        from backend.models.user import User
        from backend.repositories.telegram_repository import TelegramRepository
        from backend.services.timezone_service import TimezoneService

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
            event = db.query(Event).filter(Event.id == notif.event_id).first()
            if not event:
                notif.sent = True
                db.commit()
                continue

            user  = db.query(User).filter(User.id == notif.user_id).first()
            if not user or not user.notification_enabled:
                notif.sent = True
                db.commit()
                continue

            tg = TelegramRepository.get_by_user_id(db, notif.user_id)
            if not tg or not tg.telegram_chat_id:
                continue

            # Convert event start time to user's local timezone for display
            user_tz = getattr(user, "timezone", "Asia/Kolkata")
            local_start = TimezoneService.to_user_tz(event.start_datetime, user_tz)
            time_str = local_start.strftime("%I:%M %p") if local_start else "soon"
            reminder_minutes = getattr(user, "reminder_minutes", 15)

            message = (
                f"⏰ <b>Reminder</b>\n\n"
                f"<b>{event.title}</b> starts in {reminder_minutes} minute(s) at {time_str}.\n\n"
                f"Stay on schedule! 🚀"
            )
            sent = telegram.send_message(tg.telegram_chat_id, message)

            if sent:
                notif.sent = True
                db.commit()

                # SSE broadcast
                try:
                    from backend.api.sse import broadcast_event
                    broadcast_event(notif.user_id, "notification_sent", {
                        "event_id": event.id,
                        "title": event.title,
                    })
                except Exception:
                    pass

    except Exception as exc:
        print(f"[Scheduler] check_notifications error: {exc}")
    finally:
        db.close()


# ── Job 2: Per-user Daily Briefing (runs every minute, checks local time) ─────

# Track which users have already received their briefing today (UTC date)
# { user_id: "YYYY-MM-DD" }  — resets when the UTC date changes
_briefing_sent_today: dict[int, str] = {}


def send_daily_briefings():
    """
    Runs every minute. For each connected user:
      1. Gets the current time in their timezone.
      2. If it matches their configured briefing_time (HH:MM) and they haven't
         received a briefing today, send it.

    This approach supports per-user configurable briefing times in their
    local timezone, regardless of UTC offset.
    """
    db = SessionLocal()
    try:
        from backend.models.telegram_account import TelegramAccount
        from backend.models.user import User
        from backend.services.timezone_service import TimezoneService

        settings = _get_settings()
        telegram  = _get_telegram_provider()

        linked_accounts = (
            db.query(TelegramAccount)
            .filter(
                TelegramAccount.is_connected == True,       # noqa: E712
                TelegramAccount.telegram_chat_id.isnot(None),
            )
            .all()
        )

        today_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        for account in linked_accounts:
            try:
                user = db.query(User).filter(User.id == account.user_id).first()
                if not user or not user.is_active:
                    continue
                if not getattr(user, "notification_enabled", True):
                    continue
                if not getattr(user, "briefing_enabled", True):
                    continue

                user_tz      = getattr(user, "timezone", "Asia/Kolkata")
                briefing_time = getattr(user, "briefing_time", "07:00")

                # Current time in user's local timezone
                now_local = TimezoneService.now_in_tz(user_tz)
                current_hhmm = now_local.strftime("%H:%M")

                # Check if briefing time matches and not already sent today
                last_sent = _briefing_sent_today.get(user.id)
                if current_hhmm == briefing_time and last_sent != today_utc:
                    _briefing_sent_today[user.id] = today_utc
                    _send_briefing_for_user(db, account, user, telegram)

            except Exception as exc:
                print(f"[Scheduler] briefing error for user {account.user_id}: {exc}")

    except Exception as exc:
        print(f"[Scheduler] send_daily_briefings error: {exc}")
    finally:
        db.close()


def _send_briefing_for_user(db, account, user, telegram):
    """Send a personalized daily briefing to a single user."""
    from backend.models.event import Event, EventStatus
    from backend.repositories.expense_repository import ExpenseRepository
    from backend.repositories.analytics_repository import StreakRepository
    from backend.services.timezone_service import TimezoneService

    user_tz = getattr(user, "timezone", "Asia/Kolkata")

    # Today's events in user's timezone
    day_start, day_end = TimezoneService.day_bounds_utc(user_tz)
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

    # Productivity streak
    prod_streak = StreakRepository.get_or_create(db, account.user_id, "productivity")

    # Build schedule lines with local time display
    schedule_lines = "\n".join([
        f"  • {TimezoneService.to_user_tz(e.start_datetime, user_tz).strftime('%I:%M %p')} — {e.title}"
        for e in today_events
    ]) or "  No events scheduled for today."

    now_local = TimezoneService.now_in_tz(user_tz)
    greeting_name = user.full_name.split()[0] if user.full_name else "there"

    message = (
        f"☀️ <b>Good Morning, {greeting_name}!</b>\n\n"
        f"📅 <b>Today's Schedule</b>\n{schedule_lines}\n\n"
        f"💰 <b>Budget Today</b>: ₹{daily_spend:.2f} spent\n\n"
        f"🔥 <b>Productivity Streak</b>: {prod_streak.current_count} day(s)\n\n"
        f"Have a productive day! 💪"
    )

    telegram.send_message(account.telegram_chat_id, message)
    print(f"[Scheduler] Daily briefing sent to user {account.user_id} at {now_local.strftime('%H:%M')} {user_tz}")


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

    # Per-user daily briefing check every minute
    _scheduler.add_job(
        send_daily_briefings,
        trigger=IntervalTrigger(minutes=1),
        id="daily_briefing_checker",
        replace_existing=True,
        misfire_grace_time=30,
    )

    _scheduler.start()
    print("[Scheduler] Started — notification checker + per-user daily briefing (every minute)")


def stop_scheduler():
    """Call at app shutdown."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        print("[Scheduler] Stopped.")
