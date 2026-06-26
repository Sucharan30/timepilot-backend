"""
backend/schemas/saving_goals.py

Request/Response schemas for the Savings Goals API.
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, field_validator


class SavingGoalCreate(BaseModel):
    goal_name: str
    target_amount: Decimal
    description: Optional[str] = None
    deadline: Optional[datetime] = None
    current_saved: Optional[Decimal] = Decimal("0")

    @field_validator("target_amount")
    @classmethod
    def validate_target(cls, v):
        if v <= 0:
            raise ValueError("target_amount must be positive")
        return v


class SavingGoalUpdate(BaseModel):
    goal_name: Optional[str] = None
    description: Optional[str] = None
    target_amount: Optional[Decimal] = None
    current_saved: Optional[Decimal] = None
    deadline: Optional[datetime] = None
    status: Optional[str] = None


class AddSavingsRequest(BaseModel):
    amount: Decimal

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v):
        if v <= 0:
            raise ValueError("amount must be positive")
        return v


class SavingGoalOut(BaseModel):
    id: int
    goal_name: str
    description: Optional[str] = None
    target_amount: Decimal
    current_saved: Decimal
    progress_percent: float
    deadline: Optional[datetime] = None
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_model(cls, goal) -> "SavingGoalOut":
        target = float(goal.target_amount)
        saved  = float(goal.current_saved)
        progress = min(100.0, (saved / target * 100) if target > 0 else 0)
        return cls(
            id=goal.id,
            goal_name=goal.goal_name,
            description=goal.description,
            target_amount=goal.target_amount,
            current_saved=goal.current_saved,
            progress_percent=round(progress, 2),
            deadline=goal.deadline,
            status=goal.status.value if hasattr(goal.status, "value") else str(goal.status),
            created_at=goal.created_at,
            updated_at=goal.updated_at,
        )
