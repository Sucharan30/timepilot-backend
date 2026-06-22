"""
backend/api/expenses.py

Expense tracking endpoints (all JWT-protected, user-scoped):

  POST   /expenses           — log a new expense
  POST   /expenses/parse     — Gemini NLP parse of expense message
  GET    /expenses           — list all expenses
  GET    /expenses/{id}      — get single expense
  PUT    /expenses/{id}      — update expense
  DELETE /expenses/{id}      — delete expense
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from backend.core.dependencies import get_db, get_current_user
from backend.schemas.expense import (
    ExpenseCreate, ExpenseParseRequest, ExpenseResponse, ExpenseUpdate,
)
from backend.schemas.response import ok
from backend.services.expense_service import ExpenseService
from backend.services.gemini_expense_parser import gemini_expense_parser

router = APIRouter(prefix="/expenses", tags=["Expenses"])


# ── POST /expenses/parse ──────────────────────────────────────────────────────

@router.post("/parse")
def parse_expense(
    body: ExpenseParseRequest,
    current_user=Depends(get_current_user),
):
    """
    Send a free-text expense message to Gemini and receive structured data.
    Does NOT save to DB. Use POST /expenses to save after review.
    """
    parsed = gemini_expense_parser.parse(body.message)
    return ok({"parsed_data": parsed})


# ── POST /expenses ────────────────────────────────────────────────────────────

@router.post("", status_code=status.HTTP_201_CREATED)
def create_expense(
    body: ExpenseCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Log a new expense for the authenticated user."""
    expense = ExpenseService.create_expense(user_id=current_user.id, payload=body, db=db)
    return ok(ExpenseResponse.model_validate(expense).model_dump())


# ── GET /expenses ─────────────────────────────────────────────────────────────

@router.get("")
def list_expenses(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Return all expenses for the authenticated user."""
    expenses = ExpenseService.list_expenses(user_id=current_user.id, db=db)
    return ok([ExpenseResponse.model_validate(e).model_dump() for e in expenses])


# ── GET /expenses/{expense_id} ────────────────────────────────────────────────

@router.get("/{expense_id}")
def get_expense(
    expense_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get a single expense by ID."""
    expense = ExpenseService.get_expense(user_id=current_user.id, expense_id=expense_id, db=db)
    return ok(ExpenseResponse.model_validate(expense).model_dump())


# ── PUT /expenses/{expense_id} ────────────────────────────────────────────────

@router.put("/{expense_id}")
def update_expense(
    expense_id: int,
    body: ExpenseUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Partially update an expense."""
    expense = ExpenseService.update_expense(
        user_id=current_user.id, expense_id=expense_id, payload=body, db=db
    )
    return ok(ExpenseResponse.model_validate(expense).model_dump())


# ── DELETE /expenses/{expense_id} ─────────────────────────────────────────────

@router.delete("/{expense_id}", status_code=status.HTTP_200_OK)
def delete_expense(
    expense_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Delete an expense permanently."""
    ExpenseService.delete_expense(user_id=current_user.id, expense_id=expense_id, db=db)
    return ok({"message": f"Expense {expense_id} deleted successfully."})
