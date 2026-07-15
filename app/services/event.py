import datetime
from typing import Optional
import discord
from app.core.logger import get_logger

logger = get_logger(__name__)


class EventService:
    """
    Pure business service for managing Discord Guild Scheduled Events.
    No LLM client or prompt parsing logic here.
    """

    async def create_event(
        self,
        guild: discord.Guild,
        name: str,
        start_time: datetime.datetime,
        end_time: Optional[datetime.datetime] = None,
        description: Optional[str] = None,
        location: Optional[str] = None,
        channel_id: Optional[str] = None,
    ) -> discord.ScheduledEvent:
        """
        Creates a scheduled event in the Discord Guild.
        """
        # Ensure start_time has timezone info
        if start_time.tzinfo is None:
            tz = datetime.timezone(datetime.timedelta(hours=7))
            start_time = start_time.replace(tzinfo=tz)

        # Discord requires the start time of the event to be in the future
        now = datetime.datetime.now(datetime.timezone.utc)
        if start_time < now:
            start_time = now + datetime.timedelta(minutes=5)
            logger.info(
                f"Start time is in the past. Automatically adjusted to: {start_time}"
            )

        # Default end time to 1 hour after start time if not provided
        if not end_time:
            end_time = start_time + datetime.timedelta(hours=1)
        else:
            if end_time.tzinfo is None:
                tz = datetime.timezone(datetime.timedelta(hours=7))
                end_time = end_time.replace(tzinfo=tz)
            if end_time <= start_time:
                end_time = start_time + datetime.timedelta(hours=1)

        # Handle voice channel if channel_id is provided
        voice_channel = None
        if channel_id:
            try:
                voice_channel = guild.get_channel(int(channel_id))
            except Exception as e:
                logger.warning(
                    f"Could not retrieve voice channel with ID {channel_id}: {e}"
                )

        # Create scheduled event on the Guild
        if voice_channel:
            event = await guild.create_scheduled_event(
                name=name,
                description=description or "",
                start_time=start_time,
                end_time=end_time,
                entity_type=discord.EntityType.voice,
                channel=voice_channel,
                privacy_level=discord.PrivacyLevel.guild_only,
            )
            logger.info(
                f"Created voice scheduled event '{name}' in channel '{voice_channel.name}'"
            )
        else:
            event = await guild.create_scheduled_event(
                name=name,
                description=description or "",
                start_time=start_time,
                end_time=end_time,
                entity_type=discord.EntityType.external,
                location=location or "Discord Server",
                privacy_level=discord.PrivacyLevel.guild_only,
            )
            logger.info(
                f"Created external scheduled event '{name}' at location '{location}'"
            )

        return event
