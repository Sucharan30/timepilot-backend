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
    ) -> Event:
        """Persist a new event and return it."""
        event = Event(
            user_id=user_id,
            title=title,
            description=description,
            event_type=event_type,
            start_datetime=start_datetime,
            end_datetime=end_datetime,
            status=EventStatus.scheduled,
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
    def get_today_for_user(db: Session, user_id: int) -> List[Event]:
        """Return events whose start_datetime falls within today (UTC)."""
        now_utc   = datetime.now(timezone.utc)
        day_start = now_utc.replace(hour=0,  minute=0,  second=0,  microsecond=0)
        day_end   = now_utc.replace(hour=23, minute=59, second=59, microsecond=999999)
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
    def get_tasks_due_today(db: Session, user_id: int) -> List[Event]:
        """Return task-type events due today (UTC)."""
        now_utc   = datetime.now(timezone.utc)
        day_start = now_utc.replace(hour=0,  minute=0,  second=0,  microsecond=0)
        day_end   = now_utc.replace(hour=23, minute=59, second=59, microsecond=999999)
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
