"""
backend/schemas/expense.py

Pydantic schemas for Expense and Budget endpoints.
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, field_validator


# ── Expense ───────────────────────────────────────────────────────────────────

class ExpenseCreate(BaseModel):
    amount:       Decimal
    category:     str
    description:  Optional[str] = None
    expense_date: datetime

    @field_validator("amount")
    @classmethod
    def positive_amount(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("amount must be greater than 0")
        return v

    @field_validator("category")
    @classmethod
    def category_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("category must not be blank")
        return v.strip().lower()


class ExpenseUpdate(BaseModel):
    amount:       Optional[Decimal] = None
    category:     Optional[str]     = None
    description:  Optional[str]     = None
    expense_date: Optional[datetime] = None


class ExpenseResponse(BaseModel):
    id:           int
    user_id:      int
    amount:       Decimal
    category:     str
    description:  Optional[str]
    expense_date: datetime
    created_at:   datetime

    model_config = {"from_attributes": True}


# ── Budget ────────────────────────────────────────────────────────────────────

class BudgetCreate(BaseModel):
    category:      str
    monthly_limit: Decimal

    @field_validator("monthly_limit")
    @classmethod
    def positive_limit(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("monthly_limit must be greater than 0")
        return v

    @field_validator("category")
    @classmethod
    def category_not_blank(cls, v: str) -> str:
        return v.strip().lower()


class BudgetUpdate(BaseModel):
    category:      Optional[str]     = None
    monthly_limit: Optional[Decimal] = None


class BudgetResponse(BaseModel):
    id:            int
    user_id:       int
    category:      str
    monthly_limit: Decimal
    created_at:    datetime

    model_config = {"from_attributes": True}


class BudgetAlertResponse(BaseModel):
    category:      str
    monthly_limit: Decimal
    spent:         Decimal
    percentage:    float
    status:        str    # "ok" | "warning" | "exceeded"


# ── Expense Parse ─────────────────────────────────────────────────────────────

class ExpenseParseRequest(BaseModel):
    message: str

    @field_validator("message")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("message must not be blank")
        return v.strip()
