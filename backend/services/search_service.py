"""
backend/services/search_service.py

Production-ready full-text search across events, tasks, appointments,
reminders, deadlines, and expenses.

GET /search?q=<query>&category=all|events|expenses&limit=20

Results are grouped by entity type and returned with timezone-converted datetimes.
"""
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from backend.models.event import Event, EventStatus
from backend.models.expense import Expense
from backend.services.timezone_service import TimezoneService


class SearchService:

    @staticmethod
    def search(
        db: Session,
        user_id: int,
        q: str,
        user_timezone: Optional[str] = None,
        category: str = "all",
        limit: int = 20,
    ) -> dict:
        """
        Search events and expenses for the given user.
        Returns grouped results with timezone-converted datetimes.

        category options: "all", "events", "tasks", "appointments",
                          "reminders", "expenses"
        """
        q = q.strip()
        if not q:
            return {"events": [], "expenses": [], "total": 0}

        results: dict = {"events": [], "expenses": [], "total": 0}
        search_term = f"%{q}%"

        if category in ("all", "events", "tasks", "appointments", "reminders"):
            events = (
                db.query(Event)
                .filter(
                    Event.user_id == user_id,
                    Event.status != EventStatus.cancelled,
                    or_(
                        Event.title.ilike(search_term),
                        Event.description.ilike(search_term),
                    ),
                )
                .order_by(Event.start_datetime.desc())
                .limit(limit)
                .all()
            )
            
            results["events"] = []
            results["tasks"] = []
            
            for e in events:
                event_type_val = e.event_type.value if hasattr(e.event_type, "value") else str(e.event_type)
                item = {
                    "id": e.id,
                    "title": e.title,
                    "description": e.description,
                    "event_type": event_type_val,
                    "status": e.status.value if hasattr(e.status, "value") else str(e.status),
                    "start_datetime": TimezoneService.format_for_display(e.start_datetime, user_timezone),
                    "end_datetime": TimezoneService.format_for_display(e.end_datetime, user_timezone),
                    "entity_type": "event",
                }
                if event_type_val == "task":
                    results["tasks"].append(item)
                else:
                    results["events"].append(item)

        if category in ("all", "expenses"):
            expenses = (
                db.query(Expense)
                .filter(
                    Expense.user_id == user_id,
                    or_(
                        Expense.category.ilike(search_term),
                        Expense.description.ilike(search_term),
                    ),
                )
                .order_by(Expense.created_at.desc())
                .limit(limit)
                .all()
            )
            results["expenses"] = [
                {
                    "id": e.id,
                    "amount": float(e.amount),
                    "category": e.category,
                    "description": e.description,
                    "date": TimezoneService.format_for_display(e.expense_date, user_timezone),
                    "entity_type": "expense",
                }
                for e in expenses
            ]

        results["total"] = len(results["events"]) + len(results["expenses"])
        results["query"] = q
        return results
