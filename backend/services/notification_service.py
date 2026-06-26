"""
backend/services/notification_service.py

Notification management service.

Responsibilities:
  - schedule_event_notification: create Notification rows when events are created
  - get_settings / update_settings: manage per-user notification preferences
"""
from datetime import timedelta
from typing import Optional

from sqlalchemy.orm import Session

from backend.models.event import Event
from backend.models.notification import Notification
from backend.models.user import User
from backend.repositories.user_repository import UserRepository
from backend.services.timezone_service import TimezoneService


class NotificationService:

    @staticmethod
    def schedule_event_notification(db: Session, event: Event, user: User) -> Optional[Notification]:
        """
        Create a Notification row for an event.

        The notification fires `user.reminder_minutes` before the event starts.
        If the event is in the past (or notification would be in the past), skip.

        Returns the created Notification or None if skipped.
        """
        if not user.notification_enabled:
            return None

        # Check event type is in user's enabled categories
        enabled_categories = (user.notification_categories or "").split(",")
        event_type_str = event.event_type.value if hasattr(event.event_type, "value") else str(event.event_type)
        if enabled_categories and event_type_str not in enabled_categories:
            return None

        reminder_minutes = user.reminder_minutes or 15
        notification_time = event.start_datetime - timedelta(minutes=reminder_minutes)

        # Don't schedule if notification time is already in the past
        now_utc = TimezoneService.now_utc()
        if notification_time.tzinfo is None:
            import pytz
            notification_time = pytz.utc.localize(notification_time)

        if notification_time <= now_utc:
            return None

        notification = Notification(
            user_id=event.user_id,
            event_id=event.id,
            notification_time=notification_time,
            sent=False,
        )
        db.add(notification)
        db.commit()
        db.refresh(notification)
        print(f"[NotificationService] Scheduled reminder for event_id={event.id} at {notification_time}")
        return notification

    @staticmethod
    def get_settings(user: User) -> dict:
        """Return the current notification settings for a user."""
        return {
            "notification_enabled": user.notification_enabled,
            "reminder_minutes": user.reminder_minutes,
            "briefing_enabled": user.briefing_enabled,
            "briefing_time": user.briefing_time,
            "notification_categories": (user.notification_categories or "").split(","),
            "timezone": user.timezone,
        }

    @staticmethod
    def update_settings(
        db: Session,
        user: User,
        notification_enabled: Optional[bool] = None,
        reminder_minutes: Optional[int] = None,
        briefing_enabled: Optional[bool] = None,
        briefing_time: Optional[str] = None,
        notification_categories: Optional[list] = None,
        timezone: Optional[str] = None,
    ) -> dict:
        """
        Update notification settings for a user.
        Only fields provided (non-None) will be changed.
        """
        # Validate timezone if provided
        if timezone and not TimezoneService.validate_iana(timezone):
            raise ValueError(f"Invalid IANA timezone: {timezone}")

        # Convert category list to comma-separated string
        categories_str = None
        if notification_categories is not None:
            categories_str = ",".join(notification_categories)

        UserRepository.update_notification_settings(
            db=db,
            user=user,
            notification_enabled=notification_enabled,
            reminder_minutes=reminder_minutes,
            briefing_enabled=briefing_enabled,
            briefing_time=briefing_time,
            notification_categories=categories_str,
            timezone=timezone,
        )

        return NotificationService.get_settings(user)
