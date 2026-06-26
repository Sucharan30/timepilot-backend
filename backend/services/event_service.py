"""
backend/services/event_service.py

Business logic layer for events.
The API layer calls only this service — never repositories directly.

Enhancements:
  - Auto-schedules Telegram notifications when events are created.
  - Broadcasts SSE events for real-time dashboard updates.
"""
from typing import List, Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.models.event import Event
from backend.models.user import User
from backend.repositories.event_repository import EventRepository
from backend.schemas.event import EventCreate, EventUpdate


class EventService:

    # ── Create ────────────────────────────────────────────────────────────────

    @staticmethod
    def create_event(user_id: int, payload: EventCreate, db: Session, user: User = None) -> Event:
        """
        Create and persist a new event for the authenticated user.
        Also:
          - Converts start/end datetimes to UTC if they're timezone-aware.
          - Schedules a Telegram notification (if user has notifications enabled).
          - Broadcasts an SSE event to connected dashboard clients.
        """
        from backend.services.timezone_service import TimezoneService

        # Ensure datetimes are UTC-aware before storing
        start_utc = payload.start_datetime
        if start_utc and start_utc.tzinfo is None:
            import pytz
            start_utc = pytz.utc.localize(start_utc)

        end_utc = payload.end_datetime
        if end_utc and end_utc.tzinfo is None:
            import pytz
            end_utc = pytz.utc.localize(end_utc)

        event = EventRepository.create(
            db=db,
            user_id=user_id,
            title=payload.title,
            description=payload.description,
            event_type=payload.event_type,
            start_datetime=start_utc,
            end_datetime=end_utc,
        )

        # Auto-schedule notification if we have the user object
        if user:
            try:
                from backend.services.notification_service import NotificationService
                NotificationService.schedule_event_notification(db, event, user)
            except Exception as exc:
                print(f"[EventService] Failed to schedule notification for event {event.id}: {exc}")

        # Broadcast SSE event
        try:
            from backend.api.sse import broadcast_event
            broadcast_event(user_id, "event_created", {
                "event_id": event.id,
                "title": event.title,
                "start_datetime": str(event.start_datetime),
            })
        except Exception:
            pass  # SSE is fire-and-forget

        return event

    # ── Read ──────────────────────────────────────────────────────────────────

    @staticmethod
    def get_event(user_id: int, event_id: int, db: Session) -> Event:
        """
        Fetch a single event by ID, scoped to the user.
        Raises 404 if not found.
        """
        event = EventRepository.get_by_id(db, event_id, user_id)
        if event is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Event {event_id} not found.",
            )
        return event

    @staticmethod
    def list_events(user_id: int, db: Session) -> List[Event]:
        """Return all events for the authenticated user."""
        return EventRepository.get_all_for_user(db, user_id)

    @staticmethod
    def get_today_events(user_id: int, db: Session, user_timezone: str = None) -> List[Event]:
        """
        Return today's events in the user's local timezone.
        Uses timezone-aware day boundary calculation so "today" means
        the user's calendar day, not UTC day.
        """
        from backend.services.timezone_service import TimezoneService
        day_start, day_end = TimezoneService.day_bounds_utc(user_timezone)
        return EventRepository.get_for_period(db, user_id, day_start, day_end)

    # ── Update ────────────────────────────────────────────────────────────────

    @staticmethod
    def update_event(user_id: int, event_id: int, payload: EventUpdate, db: Session) -> Event:
        """
        Apply partial updates to an event.
        Only non-None fields in the payload are applied.
        Raises 404 if the event doesn't belong to the user.
        """
        event = EventRepository.get_by_id(db, event_id, user_id)
        if event is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Event {event_id} not found.",
            )
        update_fields = payload.model_dump(exclude_none=True)

        # Ensure datetime fields are UTC-aware
        for dt_field in ("start_datetime", "end_datetime"):
            if dt_field in update_fields and update_fields[dt_field]:
                dt = update_fields[dt_field]
                if dt.tzinfo is None:
                    import pytz
                    update_fields[dt_field] = pytz.utc.localize(dt)

        event = EventRepository.update(db, event, **update_fields)

        # Broadcast SSE
        try:
            from backend.api.sse import broadcast_event
            broadcast_event(user_id, "event_updated", {"event_id": event_id})
        except Exception:
            pass

        return event

    # ── Delete ────────────────────────────────────────────────────────────────

    @staticmethod
    def delete_event(user_id: int, event_id: int, db: Session) -> None:
        """
        Delete an event.
        Raises 404 if the event doesn't belong to the user.
        """
        event = EventRepository.get_by_id(db, event_id, user_id)
        if event is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Event {event_id} not found.",
            )
        EventRepository.delete(db, event)

        # Broadcast SSE
        try:
            from backend.api.sse import broadcast_event
            broadcast_event(user_id, "event_deleted", {"event_id": event_id})
        except Exception:
            pass
