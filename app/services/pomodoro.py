import datetime
from typing import Dict, Any, Tuple, Optional
from app.core.logger import get_logger
from app.services.database import DatabaseService
from app.services.gacha import GachaService

logger = get_logger(__name__)


class PomodoroService:
    def __init__(self, db_service: DatabaseService, gacha_service: GachaService):
        self.db_service = db_service
        self.gacha_service = gacha_service

    async def start_session(
        self,
        discord_id: str,
        channel_id: str,
        text_channel_id: str,
        duration_mins: int = 25,
    ) -> Tuple[bool, str]:
        """Start a new Pomodoro session for the user."""
        db = await self.db_service.get_db()
        await self.gacha_service.check_or_create_user(db, discord_id)

        # Check if user already has an active session
        async with db.execute(
            "SELECT pomodoro_start_time FROM users WHERE discord_id = ?", (discord_id,)
        ) as cursor:
            row = await cursor.fetchone()

        if row and row[0] is not None:
            return False, "You already have an active Pomodoro session!"

        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        await db.execute(
            """
            UPDATE users 
            SET pomodoro_start_time = ?, pomodoro_channel_id = ?, pomodoro_text_channel_id = ?, pomodoro_duration_mins = ? 
            WHERE discord_id = ?
            """,
            (now_iso, channel_id, text_channel_id, duration_mins, discord_id),
        )
        await db.commit()
        logger.info(
            f"User {discord_id} started Pomodoro in voice channel {channel_id} (text channel: {text_channel_id}) for {duration_mins} mins."
        )
        return (
            True,
            f"Focus session started! Stay in your voice channel for {duration_mins} minutes to earn rewards.",
        )

    async def get_active_session(self, discord_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve the active Pomodoro session details for the user."""
        db = await self.db_service.get_db()
        async with db.execute(
            "SELECT pomodoro_start_time, pomodoro_channel_id, pomodoro_text_channel_id, pomodoro_duration_mins FROM users WHERE discord_id = ?",
            (discord_id,),
        ) as cursor:
            row = await cursor.fetchone()

        if not row or row[0] is None:
            return None

        return {
            "start_time": datetime.datetime.fromisoformat(row[0]),
            "channel_id": row[1],
            "text_channel_id": row[2],
            "duration_mins": row[3],
        }

    async def check_session_status(self, discord_id: str) -> Tuple[bool, int, int]:
        """
        Check if user's focus session is completed.
        Returns: (is_completed, elapsed_seconds, remaining_seconds)
        """
        session = await self.get_active_session(discord_id)
        if not session:
            return False, 0, 0

        now = datetime.datetime.now(datetime.timezone.utc)
        elapsed = (now - session["start_time"]).total_seconds()
        target = session["duration_mins"] * 60

        is_completed = elapsed >= target
        remaining = max(0, int(target - elapsed))

        return is_completed, int(elapsed), remaining

    async def complete_session(
        self, discord_id: str
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """Complete the active focus session, award FP & Fruits, and reward active pet."""
        db = await self.db_service.get_db()
        session = await self.get_active_session(discord_id)
        if not session:
            return False, "You do not have an active focus session.", {}

        # Reset session fields in DB
        await db.execute(
            """
            UPDATE users 
            SET pomodoro_start_time = NULL, pomodoro_channel_id = NULL, pomodoro_text_channel_id = NULL 
            WHERE discord_id = ?
            """,
            (discord_id,),
        )

        # Award 100 FP and 1 Focus Fruit
        await db.execute(
            """
            UPDATE users 
            SET focus_points = focus_points + 100, focus_fruits = focus_fruits + 1 
            WHERE discord_id = ?
            """,
            (discord_id,),
        )

        pet_reward_msg = ""
        active_pet = await self.gacha_service.get_active_pet(discord_id)
        if active_pet:
            # Grant active pet 10 XP and restore 10 HP
            new_hp = min(100, active_pet["hp"] + 10)
            new_exp = active_pet["exp"] + 10
            new_level = active_pet["level"]

            level_up = False
            if new_exp >= 100:
                new_exp -= 100
                new_level += 1
                level_up = True

            await db.execute(
                "UPDATE pets SET hp = ?, exp = ?, level = ? WHERE id = ?",
                (new_hp, new_exp, new_level, active_pet["id"]),
            )

            pet_reward_msg = f"\n💖 Your active pet **{active_pet['name']}** healed 10 HP and gained 10 XP!"
            if level_up:
                pet_reward_msg += f" (Level Up! Now Level {new_level}!)"

        await db.commit()

        # Get updated user info
        async with db.execute(
            "SELECT focus_points, focus_fruits FROM users WHERE discord_id = ?",
            (discord_id,),
        ) as cursor:
            user_row = await cursor.fetchone()

        rewards_data = {
            "focus_points": user_row[0] if user_row else 0,
            "focus_fruits": user_row[1] if user_row else 0,
        }

        logger.info(f"User {discord_id} completed Pomodoro focus session successfully.")
        return (
            True,
            f"🌟 Congratulations! Focus session completed!\n💰 Earning: **+100 Focus Points (FP)** and **+1 Focus Fruit**!{pet_reward_msg}",
            rewards_data,
        )

    async def cancel_session(
        self, discord_id: str, penalize: bool = True
    ) -> Tuple[bool, str]:
        """Cancel the active focus session. If penalize is True, deducts active pet HP."""
        db = await self.db_service.get_db()
        session = await self.get_active_session(discord_id)
        if not session:
            return False, "You do not have an active focus session to cancel."

        # Reset session fields in DB
        await db.execute(
            """
            UPDATE users 
            SET pomodoro_start_time = NULL, pomodoro_channel_id = NULL, pomodoro_text_channel_id = NULL 
            WHERE discord_id = ?
            """,
            (discord_id,),
        )

        penalty_msg = ""
        if penalize:
            active_pet = await self.gacha_service.get_active_pet(discord_id)
            if active_pet:
                # Deduct 20 HP from active pet (cannot drop below 1 HP)
                new_hp = max(1, active_pet["hp"] - 20)
                await db.execute(
                    "UPDATE pets SET hp = ? WHERE id = ?", (new_hp, active_pet["id"])
                )
                penalty_msg = f"\n💔 Due to distraction, your active pet **{active_pet['name']}** lost 20 HP! (Current HP: {new_hp}/100)"

        await db.commit()
        logger.info(f"User {discord_id} cancelled Pomodoro focus session.")
        return True, f"❌ Focus session cancelled.{penalty_msg}"
