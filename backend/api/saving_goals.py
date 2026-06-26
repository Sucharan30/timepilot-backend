"""
backend/api/saving_goals.py

Savings Goals CRUD API:
  GET    /saving-goals          — list all goals for current user
  POST   /saving-goals          — create a new goal
  GET    /saving-goals/{id}     — get a single goal
  PUT    /saving-goals/{id}     — update a goal
  DELETE /saving-goals/{id}     — delete a goal
  POST   /saving-goals/{id}/add — add savings to a goal
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.core.dependencies import get_db, get_current_user
from backend.repositories.saving_goal_repository import SavingGoalRepository
from backend.schemas.response import ok
from backend.schemas.saving_goals import (
    SavingGoalCreate,
    SavingGoalOut,
    SavingGoalUpdate,
    AddSavingsRequest,
)
from backend.services.timezone_service import TimezoneService

router = APIRouter(prefix="/saving-goals", tags=["Savings Goals"])


# ── GET /saving-goals ──────────────────────────────────────────────────────────

@router.get("")
def list_goals(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """List all savings goals for the authenticated user."""
    goals = SavingGoalRepository.get_all_for_user(db, current_user.id)
    return ok([SavingGoalOut.from_model(g) for g in goals])


# ── POST /saving-goals ─────────────────────────────────────────────────────────

@router.post("", status_code=status.HTTP_201_CREATED)
def create_goal(
    body: SavingGoalCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Create a new savings goal."""
    # Convert deadline to UTC if provided
    deadline_utc = None
    if body.deadline:
        deadline_utc = TimezoneService.to_utc(body.deadline, current_user.timezone)

    goal = SavingGoalRepository.create(
        db=db,
        user_id=current_user.id,
        goal_name=body.goal_name,
        target_amount=float(body.target_amount),
        description=body.description,
        deadline=deadline_utc,
        current_saved=float(body.current_saved or 0),
    )
    return ok(SavingGoalOut.from_model(goal))


# ── GET /saving-goals/{id} ─────────────────────────────────────────────────────

@router.get("/{goal_id}")
def get_goal(
    goal_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get a single savings goal."""
    goal = SavingGoalRepository.get_by_id(db, goal_id, current_user.id)
    if not goal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Saving goal not found.")
    return ok(SavingGoalOut.from_model(goal))


# ── PUT /saving-goals/{id} ────────────────────────────────────────────────────

@router.put("/{goal_id}")
def update_goal(
    goal_id: int,
    body: SavingGoalUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Update a savings goal (partial update)."""
    goal = SavingGoalRepository.get_by_id(db, goal_id, current_user.id)
    if not goal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Saving goal not found.")

    update_fields = body.model_dump(exclude_none=True)

    # Convert deadline to UTC
    if "deadline" in update_fields and update_fields["deadline"]:
        update_fields["deadline"] = TimezoneService.to_utc(update_fields["deadline"], current_user.timezone)

    # Convert Decimal to float for the repository
    for field in ("target_amount", "current_saved"):
        if field in update_fields:
            update_fields[field] = float(update_fields[field])

    goal = SavingGoalRepository.update(db, goal, **update_fields)
    return ok(SavingGoalOut.from_model(goal))


# ── DELETE /saving-goals/{id} ─────────────────────────────────────────────────

@router.delete("/{goal_id}", status_code=status.HTTP_200_OK)
def delete_goal(
    goal_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Delete a savings goal."""
    goal = SavingGoalRepository.get_by_id(db, goal_id, current_user.id)
    if not goal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Saving goal not found.")
    SavingGoalRepository.delete(db, goal)
    return ok({"message": "Saving goal deleted successfully."})


# ── POST /saving-goals/{id}/add ───────────────────────────────────────────────

@router.post("/{goal_id}/add")
def add_savings(
    goal_id: int,
    body: AddSavingsRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Add an amount to the current_saved balance of a goal.
    Automatically marks the goal as completed if target is reached.
    """
    goal = SavingGoalRepository.get_by_id(db, goal_id, current_user.id)
    if not goal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Saving goal not found.")
    goal = SavingGoalRepository.add_savings(db, goal, float(body.amount))
    return ok(SavingGoalOut.from_model(goal))
