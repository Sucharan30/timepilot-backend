"""
backend/services/event_service.py

Business logic layer for events.
The API layer calls only this service — never repositories directly.

Recurring events:
  - We store the RULE on the master event (is_recurring, recurrence_type, etc.)
  - Occurrences are generated DYNAMICALLY by expand_recurring() when listing events.
  - Physical child rows are ONLY created for exception edits ("edit this occurrence").
"""
from datetime import date, timedelta
from typing import List, Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.models.event import Event, RecurrenceType
from backend.models.user import User
from backend.repositories.event_repository import EventRepository
from backend.schemas.event import EventCreate, EventUpdate


# ── Recurrence Expansion ──────────────────────────────────────────────────────

def expand_recurring(event: Event, range_start, range_end) -> List[dict]:
    """
    Dynamically generate virtual occurrence dicts for a recurring master event
    within [range_start, range_end].
    Returns lightweight dicts — NOT ORM objects.
    """
    import pytz
    from datetime import datetime, timezone

    occurrences = []
    if not event.is_recurring or not event.recurrence_type or event.recurrence_type == RecurrenceType.none:
        return occurrences

    rtype = event.recurrence_type
    interval = event.recurrence_interval or 1
    end_rule = event.recurrence_end_date  # date object or None

    current = event.start_datetime
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)

    if range_start.tzinfo is None:
        range_start = range_start.replace(tzinfo=timezone.utc)
    if range_end.tzinfo is None:
        range_end = range_end.replace(tzinfo=timezone.utc)

    # Guard against infinite loops
    max_iterations = 1000
    iteration = 0

    while current <= range_end and iteration < max_iterations:
        iteration += 1
        if end_rule and current.date() > end_rule:
            break

        if current >= range_start:
            # Check if this occurrence date has an exception (edited single occurrence)
            occurrence_date_str = current.date().isoformat()
            if occurrence_date_str not in [e.exception_date for e in (event.exceptions or [])]:
                # Calculate end time offset
                end_dt = None
                if event.end_datetime:
                    duration = event.end_datetime - event.start_datetime
                    end_dt = current + duration

                occurrences.append({
                    "id": event.id,  # Same ID as master
                    "user_id": event.user_id,
                    "title": event.title,
                    "description": event.description,
                    "event_type": event.event_type,
                    "start_datetime": current,
                    "end_datetime": end_dt,
                    "status": event.status,
                    "created_at": event.created_at,
                    "updated_at": event.updated_at,
                    "is_recurring": True,
                    "recurrence_type": event.recurrence_type,
                    "recurrence_interval": interval,
                    "recurrence_end_date": end_rule,
                    "parent_event_id": None,
                    "exception_date": None,
                    "occurrence_date": occurrence_date_str,
                })

        # Advance to next occurrence
        if rtype == RecurrenceType.daily:
            current = current + timedelta(days=interval)
        elif rtype == RecurrenceType.weekly:
            current = current + timedelta(weeks=interval)
        elif rtype == RecurrenceType.monthly:
            # Add months safely
            month = current.month - 1 + interval
            year = current.year + month // 12
            month = month % 12 + 1
            try:
                import calendar
                day = min(current.day, calendar.monthrange(year, month)[1])
                current = current.replace(year=year, month=month, day=day)
            except ValueError:
                break
        elif rtype == RecurrenceType.yearly:
            try:
                current = current.replace(year=current.year + interval)
            except ValueError:
                break
        else:
            break  # custom / unknown — only show first occurrence

    return occurrences


class EventService:

    # ── Create ────────────────────────────────────────────────────────────────

    @staticmethod
    def create_event(user_id: int, payload: EventCreate, db: Session, user: User = None) -> Event:
        """
        Create a new event (or recurring master event) for the authenticated user.
        For recurring events, only the RULE is stored. Occurrences are generated dynamically.
        """
        from backend.services.timezone_service import TimezoneService
        import pytz

        start_utc = payload.start_datetime
        if start_utc and start_utc.tzinfo is None:
            start_utc = pytz.utc.localize(start_utc)

        end_utc = payload.end_datetime
        if end_utc and end_utc.tzinfo is None:
            end_utc = pytz.utc.localize(end_utc)

        event = EventRepository.create(
            db=db,
            user_id=user_id,
            title=payload.title,
            description=payload.description,
            event_type=payload.event_type,
            start_datetime=start_utc,
            end_datetime=end_utc,
            is_recurring=payload.is_recurring,
            recurrence_type=payload.recurrence_type if payload.is_recurring else RecurrenceType.none,
            recurrence_interval=payload.recurrence_interval if payload.is_recurring else 1,
            recurrence_end_date=payload.recurrence_end_date if payload.is_recurring else None,
        )

        # Auto-schedule notification for first occurrence if user has notifications enabled
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
            pass

        return event

    # ── Read ──────────────────────────────────────────────────────────────────

    @staticmethod
    def get_event(user_id: int, event_id: int, db: Session) -> Event:
        event = EventRepository.get_by_id(db, event_id, user_id)
        if event is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Event {event_id} not found.",
            )
        return event

    @staticmethod
    def list_events(user_id: int, db: Session) -> List:
        """
        Return all events including dynamically expanded recurring occurrences.
        For the general list view, expand up to 90 days into the future.
        """
        from datetime import datetime, timezone
        import pytz

        master_events = EventRepository.get_all_for_user(db, user_id)
        now = datetime.now(timezone.utc)
        range_start = now - timedelta(days=30)   # show up to 30 days in past
        range_end   = now + timedelta(days=90)   # expand up to 90 days ahead

        result = []
        for event in master_events:
            if event.parent_event_id is not None:
                # Exception event — include as-is
                result.append(event)
            elif event.is_recurring:
                # Master recurring — expand dynamically
                occurrences = expand_recurring(event, range_start, range_end)
                result.extend(occurrences)
            else:
                # Normal one-off event
                result.append(event)

        return result

    @staticmethod
    def get_today_events(user_id: int, db: Session, user_timezone: str = None) -> List:
        """
        Return today's events including expanded recurring occurrences.
        """
        from backend.services.timezone_service import TimezoneService
        day_start, day_end = TimezoneService.day_bounds_utc(user_timezone)

        master_events = EventRepository.get_all_for_user(db, user_id)
        result = []

        for event in master_events:
            if event.parent_event_id is not None:
                # Exception event — check if it falls today
                if day_start <= event.start_datetime.replace(tzinfo=__import__('datetime').timezone.utc) <= day_end:
                    result.append(event)
            elif event.is_recurring:
                occurrences = expand_recurring(event, day_start, day_end)
                result.extend(occurrences)
            else:
                # One-off — use existing repository query
                pass

        # Also add non-recurring events using the normal repository
        one_off = EventRepository.get_for_period(db, user_id, day_start, day_end)
        # Filter out recurring masters (they've been handled above)
        one_off_filtered = [e for e in one_off if not e.is_recurring and e.parent_event_id is None]
        result.extend(one_off_filtered)

        return result

    # ── Update ────────────────────────────────────────────────────────────────

    @staticmethod
    def update_event(user_id: int, event_id: int, payload: EventUpdate, db: Session) -> Event:
        """
        Apply partial updates to an event.
        For recurring events, scope can be:
          "this"   → create an exception event for this occurrence
          "future" → shorten recurrence_end_date of master
          "all"    → update the master event directly
        """
        event = EventRepository.get_by_id(db, event_id, user_id)
        if event is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Event {event_id} not found.",
            )

        update_fields = payload.model_dump(exclude_none=True)
        update_fields.pop("recurrence_edit_scope", None)  # remove scope from fields

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
    def delete_event(user_id: int, event_id: int, db: Session, scope: str = "this") -> None:
        """
        Delete an event.
        For recurring masters, scope:
          "this"   → not supported via this endpoint (need occurrence_date)
          "future" → set recurrence_end_date to yesterday
          "all"    → delete master (cascades to exceptions)
        """
        event = EventRepository.get_by_id(db, event_id, user_id)
        if event is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Event {event_id} not found.",
            )

        if event.is_recurring and scope == "future":
            # Stop the recurrence from today onwards
            today = date.today()
            event.recurrence_end_date = today - timedelta(days=1)
            db.commit()
        else:
            EventRepository.delete(db, event)

        # Broadcast SSE
        try:
            from backend.api.sse import broadcast_event
            broadcast_event(user_id, "event_deleted", {"event_id": event_id})
        except Exception:
            pass

