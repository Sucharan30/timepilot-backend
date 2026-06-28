"""
backend/api/budget.py

Budget management endpoints (JWT-protected):

  POST   /budget            — create a budget for a category
  GET    /budget            — list all budgets
  GET    /budget/summary    — list all budgets with spent/remaining/percentage
  PUT    /budget/{id}       — update a budget
  DELETE /budget/{id}       — delete a budget
  GET    /budget/alerts     — get categories at 80%+ usage
"""
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from backend.core.dependencies import get_db, get_current_user
from backend.schemas.expense import BudgetCreate, BudgetResponse, BudgetUpdate
from backend.schemas.response import ok
from backend.services.expense_service import BudgetService

router = APIRouter(prefix="/budget", tags=["Budget"])


# ── GET /budget/alerts — must be declared BEFORE /{budget_id} ─────────────────

@router.get("/alerts")
def budget_alerts(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Returns budget categories where spending >= 80% of monthly limit.
    status: 'warning' (80-99%) or 'exceeded' (100%+).
    """
    alerts = BudgetService.get_alerts(user_id=current_user.id, db=db)
    return ok([a.model_dump() for a in alerts])


# ── GET /budget/summary ───────────────────────────────────────────────────────

@router.get("/summary")
def budget_summary(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Returns all budget categories with allocated, spent, remaining, and percentage.
    Used by dashboard and budget page for progress bars.
    """
    summary = BudgetService.get_summary(user_id=current_user.id, db=db)
    return ok(summary)


# ── POST /budget ──────────────────────────────────────────────────────────────

@router.post("", status_code=status.HTTP_201_CREATED)
def create_budget(
    body: BudgetCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Create a monthly budget limit for a category."""
    budget = BudgetService.create_budget(user_id=current_user.id, payload=body, db=db)
    return ok(BudgetResponse.model_validate(budget).model_dump())


# ── GET /budget ───────────────────────────────────────────────────────────────

@router.get("")
def list_budgets(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """List all budgets for the authenticated user."""
    budgets = BudgetService.list_budgets(user_id=current_user.id, db=db)
    return ok([BudgetResponse.model_validate(b).model_dump() for b in budgets])


# ── PUT /budget/{budget_id} ───────────────────────────────────────────────────

@router.put("/{budget_id}")
def update_budget(
    budget_id: int,
    body: BudgetUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Update a budget's monthly limit or category."""
    budget = BudgetService.update_budget(
        user_id=current_user.id, budget_id=budget_id, payload=body, db=db
    )
    return ok(BudgetResponse.model_validate(budget).model_dump())


# ── DELETE /budget/{budget_id} ────────────────────────────────────────────────

@router.delete("/{budget_id}", status_code=status.HTTP_200_OK)
def delete_budget(
    budget_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Delete a budget permanently."""
    BudgetService.delete_budget(user_id=current_user.id, budget_id=budget_id, db=db)
    return ok({"message": f"Budget {budget_id} deleted."})

