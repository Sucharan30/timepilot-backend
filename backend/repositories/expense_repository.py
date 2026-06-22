"""
backend/repositories/expense_repository.py

Data-access layer for expenses and budgets tables.
"""
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.models.expense import Budget, Expense


# ── Expense Repository ────────────────────────────────────────────────────────

class ExpenseRepository:

    @staticmethod
    def create(
        db: Session,
        user_id: int,
        amount: Decimal,
        category: str,
        expense_date: datetime,
        description: Optional[str] = None,
    ) -> Expense:
        expense = Expense(
            user_id=user_id,
            amount=amount,
            category=category,
            description=description,
            expense_date=expense_date,
        )
        db.add(expense)
        db.commit()
        db.refresh(expense)
        return expense

    @staticmethod
    def get_by_id(db: Session, expense_id: int, user_id: int) -> Optional[Expense]:
        return (
            db.query(Expense)
            .filter(Expense.id == expense_id, Expense.user_id == user_id)
            .first()
        )

    @staticmethod
    def get_all_for_user(db: Session, user_id: int) -> List[Expense]:
        return (
            db.query(Expense)
            .filter(Expense.user_id == user_id)
            .order_by(Expense.expense_date.desc())
            .all()
        )

    @staticmethod
    def get_for_period(
        db: Session, user_id: int, start: datetime, end: datetime
    ) -> List[Expense]:
        return (
            db.query(Expense)
            .filter(
                Expense.user_id == user_id,
                Expense.expense_date >= start,
                Expense.expense_date <= end,
            )
            .order_by(Expense.expense_date.desc())
            .all()
        )

    @staticmethod
    def get_monthly_total_by_category(
        db: Session, user_id: int, year: int, month: int
    ) -> dict:
        """Returns {category: total_spent} for a given month."""
        rows = (
            db.query(Expense.category, func.sum(Expense.amount))
            .filter(
                Expense.user_id == user_id,
                func.year(Expense.expense_date) == year,
                func.month(Expense.expense_date) == month,
            )
            .group_by(Expense.category)
            .all()
        )
        return {row[0]: float(row[1]) for row in rows}

    @staticmethod
    def update(db: Session, expense: Expense, **fields) -> Expense:
        for field, value in fields.items():
            if value is not None and hasattr(expense, field):
                setattr(expense, field, value)
        db.commit()
        db.refresh(expense)
        return expense

    @staticmethod
    def delete(db: Session, expense: Expense) -> None:
        db.delete(expense)
        db.commit()


# ── Budget Repository ─────────────────────────────────────────────────────────

class BudgetRepository:

    @staticmethod
    def create(
        db: Session, user_id: int, category: str, monthly_limit: Decimal
    ) -> Budget:
        budget = Budget(user_id=user_id, category=category, monthly_limit=monthly_limit)
        db.add(budget)
        db.commit()
        db.refresh(budget)
        return budget

    @staticmethod
    def get_by_id(db: Session, budget_id: int, user_id: int) -> Optional[Budget]:
        return (
            db.query(Budget)
            .filter(Budget.id == budget_id, Budget.user_id == user_id)
            .first()
        )

    @staticmethod
    def get_by_category(db: Session, user_id: int, category: str) -> Optional[Budget]:
        return (
            db.query(Budget)
            .filter(Budget.user_id == user_id, Budget.category == category)
            .first()
        )

    @staticmethod
    def get_all_for_user(db: Session, user_id: int) -> List[Budget]:
        return (
            db.query(Budget)
            .filter(Budget.user_id == user_id)
            .order_by(Budget.category)
            .all()
        )

    @staticmethod
    def update(db: Session, budget: Budget, **fields) -> Budget:
        for field, value in fields.items():
            if value is not None and hasattr(budget, field):
                setattr(budget, field, value)
        db.commit()
        db.refresh(budget)
        return budget

    @staticmethod
    def delete(db: Session, budget: Budget) -> None:
        db.delete(budget)
        db.commit()
