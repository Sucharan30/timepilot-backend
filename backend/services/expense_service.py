"""
backend/services/expense_service.py

Business logic for expense tracking and budget management.
"""
from datetime import datetime, timezone
from decimal import Decimal
from typing import List

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.models.expense import Budget, Expense
from backend.repositories.expense_repository import BudgetRepository, ExpenseRepository
from backend.schemas.expense import BudgetAlertResponse, BudgetCreate, BudgetUpdate, ExpenseCreate, ExpenseUpdate


class ExpenseService:

    # ── Expense CRUD ──────────────────────────────────────────────────────────

    @staticmethod
    def create_expense(user_id: int, payload: ExpenseCreate, db: Session) -> Expense:
        return ExpenseRepository.create(
            db=db,
            user_id=user_id,
            amount=payload.amount,
            category=payload.category,
            description=payload.description,
            expense_date=payload.expense_date,
        )

    @staticmethod
    def get_expense(user_id: int, expense_id: int, db: Session) -> Expense:
        expense = ExpenseRepository.get_by_id(db, expense_id, user_id)
        if expense is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Expense {expense_id} not found.")
        return expense

    @staticmethod
    def list_expenses(user_id: int, db: Session) -> List[Expense]:
        return ExpenseRepository.get_all_for_user(db, user_id)

    @staticmethod
    def update_expense(user_id: int, expense_id: int, payload: ExpenseUpdate, db: Session) -> Expense:
        expense = ExpenseRepository.get_by_id(db, expense_id, user_id)
        if expense is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Expense {expense_id} not found.")
        return ExpenseRepository.update(db, expense, **payload.model_dump(exclude_none=True))

    @staticmethod
    def delete_expense(user_id: int, expense_id: int, db: Session) -> None:
        expense = ExpenseRepository.get_by_id(db, expense_id, user_id)
        if expense is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Expense {expense_id} not found.")
        ExpenseRepository.delete(db, expense)


class BudgetService:

    # ── Budget CRUD ───────────────────────────────────────────────────────────

    @staticmethod
    def create_budget(user_id: int, payload: BudgetCreate, db: Session) -> Budget:
        # Prevent duplicate category
        existing = BudgetRepository.get_by_category(db, user_id, payload.category)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Budget for category '{payload.category}' already exists. Use PUT to update it.",
            )
        return BudgetRepository.create(db, user_id, payload.category, payload.monthly_limit)

    @staticmethod
    def get_budget(user_id: int, budget_id: int, db: Session) -> Budget:
        budget = BudgetRepository.get_by_id(db, budget_id, user_id)
        if budget is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Budget {budget_id} not found.")
        return budget

    @staticmethod
    def list_budgets(user_id: int, db: Session) -> List[Budget]:
        return BudgetRepository.get_all_for_user(db, user_id)

    @staticmethod
    def update_budget(user_id: int, budget_id: int, payload: BudgetUpdate, db: Session) -> Budget:
        budget = BudgetRepository.get_by_id(db, budget_id, user_id)
        if budget is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Budget {budget_id} not found.")
        return BudgetRepository.update(db, budget, **payload.model_dump(exclude_none=True))

    @staticmethod
    def delete_budget(user_id: int, budget_id: int, db: Session) -> None:
        budget = BudgetRepository.get_by_id(db, budget_id, user_id)
        if budget is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Budget {budget_id} not found.")
        BudgetRepository.delete(db, budget)

    @staticmethod
    def get_alerts(user_id: int, db: Session) -> List[BudgetAlertResponse]:
        """
        Compare each budget's monthly limit to actual spending this month.
        Returns alerts for categories at 80%+ usage.
        """
        now = datetime.now(timezone.utc)
        budgets = BudgetRepository.get_all_for_user(db, user_id)
        monthly_spending = ExpenseRepository.get_monthly_total_by_category(db, user_id, now.year, now.month)

        alerts = []
        for b in budgets:
            spent = Decimal(str(monthly_spending.get(b.category, 0)))
            limit = b.monthly_limit
            pct = float(spent / limit * 100) if limit > 0 else 0.0

            if pct >= 80:
                status_label = "exceeded" if pct >= 100 else "warning"
                alerts.append(BudgetAlertResponse(
                    category=b.category,
                    monthly_limit=limit,
                    spent=spent,
                    percentage=round(pct, 1),
                    status=status_label,
                ))

        return alerts

    @staticmethod
    def get_summary(user_id: int, db: Session) -> List[dict]:
        """
        Return per-category summary: allocated, spent, remaining, percentage.
        Used by budget page and dashboard for progress bars.
        """
        now = datetime.now(timezone.utc)
        budgets = BudgetRepository.get_all_for_user(db, user_id)
        monthly_spending = ExpenseRepository.get_monthly_total_by_category(db, user_id, now.year, now.month)

        result = []
        for b in budgets:
            spent = float(monthly_spending.get(b.category, 0))
            limit = float(b.monthly_limit)
            remaining = max(0, limit - spent)
            pct = round(spent / limit * 100, 1) if limit > 0 else 0.0
            alert_status = "normal"
            if pct >= 100:
                alert_status = "exceeded"
            elif pct >= 80:
                alert_status = "warning"

            result.append({
                "id": b.id,
                "category": b.category,
                "monthly_limit": limit,
                "spent": spent,
                "remaining": remaining,
                "percentage": pct,
                "status": alert_status,
            })

        return result
