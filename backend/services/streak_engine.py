"""
backend/services/streak_engine.py

Streak tracking and reward engine.

Streak types (configurable):
  - productivity   (events completed)
  - workout        (workout events)
  - study          (study/class events)
  - expense_logging (daily expense logged)

Logic:
  - A streak increments when the user performs the tracked action on consecutive days.
  - A streak resets to 0 if a day is missed.
  - Milestones (3, 7, 14, 30, 60, 100 days) trigger AI-generated reward messages.
"""
from datetime import timedelta
from typing import Optional

from sqlalchemy.orm import Session

from backend.models.streak import Streak
from backend.models.reward import RewardType
from backend.repositories.reward_repository import RewardRepository
from backend.services.timezone_service import TimezoneService

STREAK_MILESTONES = [3, 7, 14, 30, 60, 100]


class StreakEngine:

    @staticmethod
    def get_or_create_streak(db: Session, user_id: int, streak_type: str) -> Streak:
        """Fetch or create the streak record for this user + type."""
        streak = (
            db.query(Streak)
            .filter(Streak.user_id == user_id, Streak.streak_type == streak_type)
            .first()
        )
        if not streak:
            streak = Streak(user_id=user_id, streak_type=streak_type, current_count=0, longest_count=0)
            db.add(streak)
            db.commit()
            db.refresh(streak)
        return streak

    @staticmethod
    def update_streak(db: Session, user_id: int, streak_type: str) -> Streak:
        """
        Increment the streak by 1 day.
        Update longest_count if current surpasses it.
        """
        streak = StreakEngine.get_or_create_streak(db, user_id, streak_type)
        streak.current_count += 1
        if streak.current_count > streak.longest_count:
            streak.longest_count = streak.current_count
        db.commit()
        db.refresh(streak)
        return streak

    @staticmethod
    def reset_streak(db: Session, user_id: int, streak_type: str) -> Streak:
        """Reset the current streak to 0 (missed a day)."""
        streak = StreakEngine.get_or_create_streak(db, user_id, streak_type)
        streak.current_count = 0
        db.commit()
        db.refresh(streak)
        return streak

    @staticmethod
    def get_all_streaks(db: Session, user_id: int) -> list[dict]:
        """Return all streak records for a user as dicts."""
        streaks = (
            db.query(Streak)
            .filter(Streak.user_id == user_id)
            .all()
        )
        return [
            {
                "streak_type": s.streak_type,
                "current_count": s.current_count,
                "longest_count": s.longest_count,
                "updated_at": str(s.updated_at),
            }
            for s in streaks
        ]

    @staticmethod
    def check_and_reward(
        db: Session,
        user_id: int,
        streak_type: str,
        streak: Streak,
        send_telegram_fn=None,
        chat_id: Optional[str] = None,
    ) -> Optional[dict]:
        """
        If the new streak count is a milestone, generate a reward and optionally
        send a Telegram celebration message.

        Returns the reward dict or None if no milestone was reached.
        """
        if streak.current_count not in STREAK_MILESTONES:
            return None

        milestone = streak.current_count
        reward_text = StreakEngine._generate_reward_text(streak_type, milestone)
        reward_type = StreakEngine._pick_reward_type(milestone)

        reward = RewardRepository.create(
            db=db,
            user_id=user_id,
            reward_text=reward_text,
            reward_type=reward_type,
            streak_type=streak_type,
            streak_count=milestone,
        )

        if send_telegram_fn and chat_id:
            emoji = "🏆" if milestone >= 30 else "🎉"
            send_telegram_fn(
                chat_id,
                f"{emoji} <b>Streak Milestone!</b>\n\n"
                f"You've reached a <b>{milestone}-day {streak_type.replace('_', ' ')} streak!</b>\n\n"
                f"{reward_text}",
            )

        return {
            "reward_type": reward.reward_type.value,
            "reward_text": reward.reward_text,
            "streak_type": streak_type,
            "streak_count": milestone,
        }

    @staticmethod
    def _generate_reward_text(streak_type: str, days: int) -> str:
        """Simple rule-based reward text. Can be replaced with Gemini call."""
        type_name = streak_type.replace("_", " ").title()
        if days >= 100:
            return f"🌟 LEGENDARY! {days}-day {type_name} streak — you're unstoppable! Earned: Master Badge 🎖"
        elif days >= 60:
            return f"💎 DIAMOND streak! {days} days of {type_name} — you're a champion! Earned: Diamond Badge 💎"
        elif days >= 30:
            return f"🏅 30-day {type_name} milestone — incredible dedication! You've earned Free Time: Take the evening off! 🌅"
        elif days >= 14:
            return f"🔥 2-week {type_name} streak! Consistency is your superpower. Earned: Gold Badge 🏆"
        elif days >= 7:
            return f"⚡ 7-day {type_name} streak — one full week! You're building a real habit. Earned: Silver Badge 🥈"
        else:
            return f"✨ {days}-day {type_name} streak — great start! Keep it going. Earned: Starter Badge 🌟"

    @staticmethod
    def _pick_reward_type(days: int) -> RewardType:
        if days >= 30:
            return RewardType.free_time
        elif days >= 14:
            return RewardType.achievement
        elif days >= 7:
            return RewardType.badge
        else:
            return RewardType.badge
