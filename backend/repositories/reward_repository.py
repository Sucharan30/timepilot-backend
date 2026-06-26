"""
backend/repositories/reward_repository.py

Data-access layer for the rewards table.
"""
from typing import List

from sqlalchemy.orm import Session

from backend.models.reward import Reward, RewardType


class RewardRepository:

    @staticmethod
    def create(
        db: Session,
        user_id: int,
        reward_text: str,
        reward_type: RewardType = RewardType.badge,
        streak_type: str = None,
        streak_count: int = None,
    ) -> Reward:
        """Persist a new reward."""
        reward = Reward(
            user_id=user_id,
            reward_type=reward_type,
            reward_text=reward_text,
            streak_type=streak_type,
            streak_count=streak_count,
        )
        db.add(reward)
        db.commit()
        db.refresh(reward)
        return reward

    @staticmethod
    def get_for_user(db: Session, user_id: int, limit: int = 20) -> List[Reward]:
        """Return the most recent rewards for a user."""
        return (
            db.query(Reward)
            .filter(Reward.user_id == user_id)
            .order_by(Reward.created_at.desc())
            .limit(limit)
            .all()
        )
