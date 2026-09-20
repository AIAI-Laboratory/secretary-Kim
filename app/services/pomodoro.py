"""Business service for Pomodoro focus sessions and timer tracking."""

import datetime
from typing import Any

from app.core.logger import get_logger
from app.services.database import DatabaseService
from app.services.gacha import GachaService

logger = get_logger(__name__)


class PomodoroService:
    """Service managing Pomodoro focus session state, progress, and completions."""

    def __init__(
        self, db_service: DatabaseService, gacha_service: GachaService
    ) -> None:
        """Initialize PomodoroService with database and gacha services.

        Args:
            db_service (DatabaseService): Storage service for session persistence.
            gacha_service (GachaService): Service handling pet and user accounts.
        """
        self.db_service = db_service
        self.gacha_service = gacha_service

    async def start_session(
        self,
        discord_id: str,
        channel_id: str,
        text_channel_id: str,
        duration_mins: int = 25,
    ) -> tuple[bool, str]:
        """Start a new Pomodoro session for the user.

        Args:
            discord_id (str): Discord user ID.
            channel_id (str): Voice channel ID where user is focusing.
            text_channel_id (str): Text channel ID for sending notifications.
            duration_mins (int): Target session duration in minutes. Defaults to 25.

        Returns:
            tuple[bool, str]: (Success status, feedback message).
        """
        await self.gacha_service.check_or_create_user(None, discord_id)

        # Check if user already has an active session
        session = await self.get_active_session(discord_id)
        if session:
            return False, "You already have an active Pomodoro session!"

        now_iso = datetime.datetime.now(datetime.UTC).isoformat()

        await self.db_service.update_data(
            f"users/{discord_id}/pomodoro",
            {
                "start_time": now_iso,
                "channel_id": channel_id,
                "text_channel_id": text_channel_id,
                "duration_mins": duration_mins,
            },
        )

        logger.info(
            f"User {discord_id} started Pomodoro in voice channel {channel_id} (text channel: {text_channel_id}) for {duration_mins} mins."
        )
        return (
            True,
            f"Focus session started! Stay in your voice channel for {duration_mins} minutes to earn rewards.",
        )

    async def get_active_session(
        self, discord_id: str, db: Any | None = None
    ) -> dict[str, Any] | None:
        """Retrieve the active Pomodoro session details for the user.

        Args:
            discord_id (str): Discord user ID.
            db (Any | None): Optional database session. Defaults to None.

        Returns:
            dict[str, Any] | None: Session dictionary if active, else None.
        """
        pomo_data = await self.db_service.get_data(f"users/{discord_id}/pomodoro")
        if not pomo_data or not pomo_data.get("start_time"):
            return None

        return {
            "start_time": datetime.datetime.fromisoformat(pomo_data["start_time"]),
            "channel_id": pomo_data.get("channel_id"),
            "text_channel_id": pomo_data.get("text_channel_id"),
            "duration_mins": pomo_data.get("duration_mins", 25),
        }

    async def check_session_status(self, discord_id: str) -> tuple[bool, int, int]:
        """Check if user's focus session is completed.

        Args:
            discord_id (str): Discord user ID.

        Returns:
            tuple[bool, int, int]: (is_completed, elapsed_seconds, remaining_seconds).
        """
        session = await self.get_active_session(discord_id)
        if not session:
            return False, 0, 0

        now = datetime.datetime.now(datetime.UTC)
        elapsed = (now - session["start_time"]).total_seconds()
        target = session["duration_mins"] * 60

        is_completed = elapsed >= target
        remaining = max(0, int(target - elapsed))

        return is_completed, int(elapsed), remaining

    async def complete_session(
        self, discord_id: str
    ) -> tuple[bool, str, dict[str, Any]]:
        """Complete the active focus session without any currency rewards.

        Args:
            discord_id (str): Discord user ID.

        Returns:
            tuple[bool, str, dict[str, Any]]: (Success, message, result details).
        """
        session = await self.get_active_session(discord_id)
        if not session:
            return False, "You do not have an active focus session.", {}

        # Reset session fields in DB
        await self.db_service.delete_data(f"users/{discord_id}/pomodoro")

        logger.info(f"User {discord_id} completed Pomodoro focus session successfully.")
        return (
            True,
            "🌟 Congratulations! Focus session completed!",
            {},
        )

    async def cancel_session(
        self, discord_id: str, penalize: bool = True
    ) -> tuple[bool, str]:
        """Cancel the active focus session without any penalty.

        Args:
            discord_id (str): Discord user ID.
            penalize (bool): Whether to apply penalties. Defaults to True.

        Returns:
            tuple[bool, str]: (Success status, feedback message).
        """
        session = await self.get_active_session(discord_id)
        if not session:
            return False, "You do not have an active focus session to cancel."

        # Reset session fields in DB
        await self.db_service.delete_data(f"users/{discord_id}/pomodoro")

        logger.info(f"User {discord_id} cancelled Pomodoro focus session.")
        return True, "❌ Focus session cancelled."
