"""
backend/api/rewards.py

Rewards API:
  GET /rewards — list recent rewards for the current user
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.core.dependencies import get_db, get_current_user
from backend.repositories.reward_repository import RewardRepository
from backend.schemas.response import ok

router = APIRouter(prefix="/rewards", tags=["Rewards"])


@router.get("")
def get_rewards(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Return the most recent rewards earned by the authenticated user.
    Rewards are generated when streak milestones are hit (3, 7, 14, 30, 60, 100 days).
    """
    rewards = RewardRepository.get_for_user(db, current_user.id, limit=limit)
    return ok([
        {
            "id": r.id,
            "reward_type": r.reward_type.value if hasattr(r.reward_type, "value") else str(r.reward_type),
            "reward_text": r.reward_text,
            "streak_type": r.streak_type,
            "streak_count": r.streak_count,
            "earned_at": str(r.created_at),
        }
        for r in rewards
    ])
