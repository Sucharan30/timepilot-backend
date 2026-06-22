"""
backend/models/expense.py

Expense and Budget models for the financial tracking module.
"""
from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from backend.database import Base


class Expense(Base):
    __tablename__ = "expenses"

    id           = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id      = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    amount       = Column(Numeric(10, 2), nullable=False)
    category     = Column(String(100), nullable=False, index=True)
    description  = Column(Text, nullable=True)
    expense_date = Column(DateTime(timezone=True), nullable=False)
    created_at   = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # ── Relationships ──────────────────────────────────────────────────────────
    user = relationship("User", back_populates="expenses")


class Budget(Base):
    __tablename__ = "budgets"

    id            = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id       = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    category      = Column(String(100), nullable=False)
    monthly_limit = Column(Numeric(10, 2), nullable=False)
    created_at    = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # ── Relationships ──────────────────────────────────────────────────────────
    user = relationship("User", back_populates="budgets")
