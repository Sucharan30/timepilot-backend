"""
backend/repositories/event_repository.py

Data-access layer for the events and notifications tables.
All DB queries for Event/Notification go through here.
"""
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

from backend.models.event import Event, EventStatus, EventType
from backend.models.notification import Notification


class EventRepository:

    # ── Create ────────────────────────────────────────────────────────────────

    @staticmethod
    def create(
        db: Session,
        user_id: int,
        title: str,
        event_type: EventType,
        start_datetime: datetime,
        description: Optional[str] = None,
        end_datetime: Optional[datetime] = None,
        is_recurring: bool = False,
        recurrence_type=None,
        recurrence_interval: int = 1,
        recurrence_end_date=None,
        parent_event_id: Optional[int] = None,
        exception_date: Optional[str] = None,
    ) -> Event:
        """Persist a new event and return it."""
        from backend.models.event import RecurrenceType
        event = Event(
            user_id=user_id,
            title=title,
            description=description,
            event_type=event_type,
            start_datetime=start_datetime,
            end_datetime=end_datetime,
            status=EventStatus.scheduled,
            is_recurring=is_recurring,
            recurrence_type=recurrence_type or RecurrenceType.none,
            recurrence_interval=recurrence_interval,
            recurrence_end_date=recurrence_end_date,
            parent_event_id=parent_event_id,
            exception_date=exception_date,
        )
        db.add(event)
        db.commit()
        db.refresh(event)
        return event

    # ── Read ──────────────────────────────────────────────────────────────────

    @staticmethod
    def get_by_id(db: Session, event_id: int, user_id: int) -> Optional[Event]:
        """Fetch a single event that belongs to the given user."""
        return (
            db.query(Event)
            .filter(Event.id == event_id, Event.user_id == user_id)
            .first()
        )

    @staticmethod
    def get_all_for_user(db: Session, user_id: int) -> List[Event]:
        """Return all events for a user, newest first."""
        return (
            db.query(Event)
            .filter(Event.user_id == user_id)
            .order_by(Event.start_datetime.asc())
            .all()
        )

    @staticmethod
    def get_today_for_user(db: Session, user_id: int, timezone_str: Optional[str] = None) -> List[Event]:
        """Return events whose start_datetime falls within the user's local today (UTC)."""
        from backend.services.timezone_service import TimezoneService
        day_start, day_end = TimezoneService.day_bounds_utc(timezone_str)
        return (
            db.query(Event)
            .filter(
                Event.user_id == user_id,
                Event.start_datetime >= day_start,
                Event.start_datetime <= day_end,
                Event.status == EventStatus.scheduled,
            )
            .order_by(Event.start_datetime.asc())
            .all()
        )

    @staticmethod
    def get_for_period(
        db: Session,
        user_id: int,
        start_dt: datetime,
        end_dt: datetime,
        status_filter: EventStatus = EventStatus.scheduled,
    ) -> List[Event]:
        """
        Return events within an arbitrary period (used for timezone-correct day queries).
        start_dt and end_dt should be UTC-aware datetimes.
        """
        q = db.query(Event).filter(
            Event.user_id == user_id,
            Event.start_datetime >= start_dt,
            Event.start_datetime <= end_dt,
        )
        if status_filter is not None:
            q = q.filter(Event.status == status_filter)
        return q.order_by(Event.start_datetime.asc()).all()

    @staticmethod
    def get_tasks_due_today(db: Session, user_id: int, timezone_str: Optional[str] = None) -> List[Event]:
        """Return task-type events due today (in user's local timezone)."""
        from backend.services.timezone_service import TimezoneService
        day_start, day_end = TimezoneService.day_bounds_utc(timezone_str)
        return (
            db.query(Event)
            .filter(
                Event.user_id == user_id,
                Event.event_type == EventType.task,
                Event.start_datetime >= day_start,
                Event.start_datetime <= day_end,
                Event.status == EventStatus.scheduled,
            )
            .order_by(Event.start_datetime.asc())
            .all()
        )

    @staticmethod
    def count_for_user(db: Session, user_id: int) -> int:
        """Return total event count for a user."""
        return db.query(Event).filter(Event.user_id == user_id).count()

    @staticmethod
    def count_all(db: Session) -> int:
        """Return total event count across all users (for debug endpoint)."""
        return db.query(Event).count()

    # ── Update ────────────────────────────────────────────────────────────────

    @staticmethod
    def update(db: Session, event: Event, **fields) -> Event:
        """Apply arbitrary field updates to an event."""
        for field, value in fields.items():
            if value is not None and hasattr(event, field):
                setattr(event, field, value)
        db.commit()
        db.refresh(event)
        return event

    # ── Delete ────────────────────────────────────────────────────────────────

    @staticmethod
    def delete(db: Session, event: Event) -> None:
        """Hard-delete an event (cascades to notifications)."""
        db.delete(event)
        db.commit()


# ── Notification Repository ────────────────────────────────────────────────────

class NotificationRepository:

    @staticmethod
    def get_upcoming_for_user(db: Session, user_id: int, limit: int = 10) -> List[Notification]:
        """Return the next N unsent notifications for a user, ordered by time."""
        now_utc = datetime.now(timezone.utc)
        return (
            db.query(Notification)
            .filter(
                Notification.user_id == user_id,
                Notification.sent == False,             # noqa: E712
                Notification.notification_time >= now_utc,
            )
            .order_by(Notification.notification_time.asc())
            .limit(limit)
            .all()
        )
