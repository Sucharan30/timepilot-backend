"""
backend/services/event_service.py

Business logic layer for events.
The API layer calls only this service — never repositories directly.
"""
from typing import List, Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.models.event import Event
from backend.repositories.event_repository import EventRepository
from backend.schemas.event import EventCreate, EventUpdate, EventResponse


class EventService:

    # ── Create ────────────────────────────────────────────────────────────────

    @staticmethod
    def create_event(user_id: int, payload: EventCreate, db: Session) -> Event:
        """Create and persist a new event for the authenticated user."""
        return EventRepository.create(
            db=db,
            user_id=user_id,
            title=payload.title,
            description=payload.description,
            event_type=payload.event_type,
            start_datetime=payload.start_datetime,
            end_datetime=payload.end_datetime,
        )

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
    def get_today_events(user_id: int, db: Session) -> List[Event]:
        """Return today's events (UTC) for the authenticated user."""
        return EventRepository.get_today_for_user(db, user_id)

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
        return EventRepository.update(db, event, **update_fields)

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
