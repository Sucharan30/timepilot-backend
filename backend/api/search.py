"""
backend/api/search.py

Production-ready search API:
  GET /search?q=<query>&category=all|events|expenses&limit=20

Searches across all user data and returns grouped results.
If the frontend removes the search bar, this API continues to function.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.core.dependencies import get_db, get_current_user
from backend.schemas.response import ok
from backend.services.search_service import SearchService

router = APIRouter(prefix="/search", tags=["Search"])


@router.get("")
def search(
    q: str = Query(..., min_length=1, description="Search query"),
    category: str = Query("all", description="Filter: all | events | tasks | appointments | reminders | expenses"),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Search across events (meetings, tasks, appointments, reminders, deadlines)
    and expenses for the authenticated user.

    Returns results grouped by entity type with timezone-aware datetimes.
    """
    results = SearchService.search(
        db=db,
        user_id=current_user.id,
        q=q,
        user_timezone=current_user.timezone,
        category=category,
        limit=limit,
    )
    return ok(results)
