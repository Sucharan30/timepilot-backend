"""
backend/repositories/saving_goal_repository.py

Data-access layer for the saving_goals table.
Standard CRUD operations.
"""
from typing import List, Optional

from sqlalchemy.orm import Session

from backend.models.saving_goal import SavingGoal, GoalStatus


class SavingGoalRepository:

    @staticmethod
    def create(
        db: Session,
        user_id: int,
        goal_name: str,
        target_amount: float,
        description: Optional[str] = None,
        deadline=None,
        current_saved: float = 0,
    ) -> SavingGoal:
        """Persist a new saving goal."""
        goal = SavingGoal(
            user_id=user_id,
            goal_name=goal_name,
            target_amount=target_amount,
            current_saved=current_saved,
            description=description,
            deadline=deadline,
            status=GoalStatus.active,
        )
        db.add(goal)
        db.commit()
        db.refresh(goal)
        return goal

    @staticmethod
    def get_by_id(db: Session, goal_id: int, user_id: int) -> Optional[SavingGoal]:
        """Fetch a single saving goal that belongs to the given user."""
        return (
            db.query(SavingGoal)
            .filter(SavingGoal.id == goal_id, SavingGoal.user_id == user_id)
            .first()
        )

    @staticmethod
    def get_all_for_user(db: Session, user_id: int) -> List[SavingGoal]:
        """Return all saving goals for a user, newest first."""
        return (
            db.query(SavingGoal)
            .filter(SavingGoal.user_id == user_id)
            .order_by(SavingGoal.created_at.desc())
            .all()
        )

    @staticmethod
    def update(db: Session, goal: SavingGoal, **fields) -> SavingGoal:
        """Apply arbitrary field updates to a saving goal."""
        for field, value in fields.items():
            if value is not None and hasattr(goal, field):
                setattr(goal, field, value)
        db.commit()
        db.refresh(goal)
        return goal

    @staticmethod
    def delete(db: Session, goal: SavingGoal) -> None:
        """Hard-delete a saving goal."""
        db.delete(goal)
        db.commit()

    @staticmethod
    def add_savings(db: Session, goal: SavingGoal, amount: float) -> SavingGoal:
        """
        Add amount to current_saved.
        Automatically marks goal as completed if target is reached.
        """
        goal.current_saved = float(goal.current_saved) + amount
        if float(goal.current_saved) >= float(goal.target_amount):
            goal.status = GoalStatus.completed
        db.commit()
        db.refresh(goal)
        return goal
