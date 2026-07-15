import datetime
import hashlib
from typing import Any, Dict, List, Optional
import discord
from app.core.config import settings
from app.core.logger import get_logger
from app.services.database import DatabaseService

logger = get_logger(__name__)


class AttendanceService:
    """
    Service to track user presence in voice channels, reward attendance coins,
    and update the server leaderboard channel.
    """

    def __init__(self, db_service: DatabaseService):
        self.db_service = db_service
        self._last_leaderboard_hash: Optional[str] = None
        self._leaderboard_msg_id: Optional[int] = None

    async def get_user_coins(self, discord_id: str) -> Dict[str, Any]:
        """
        Get the user's current attendance coins and accumulated minutes.
        Creates the user entry with default values if they do not exist.
        """
        db = await self.db_service.get_db()
        async with db.execute(
            "SELECT attendance_coins, voice_accumulated_minutes FROM users WHERE discord_id = ?",
            (discord_id,),
        ) as cursor:
            row = await cursor.fetchone()

        if not row:
            # Insert new user with default focus values and 100 attendance values
            await db.execute(
                "INSERT INTO users (discord_id, focus_points, focus_fruits, attendance_coins, voice_accumulated_minutes) VALUES (?, ?, ?, ?, ?)",
                (discord_id, 200, 2, 100, 0),
            )
            await db.commit()
            return {"attendance_coins": 100, "voice_accumulated_minutes": 0}

        return {
            "attendance_coins": row[0] if row[0] is not None else 100,
            "voice_accumulated_minutes": row[1] or 0,
        }

    async def get_leaderboard_data(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Fetch top users ordered by coins, then by accumulated minutes.
        Only displays users with > 0 coins or minutes.
        """
        db = await self.db_service.get_db()
        async with db.execute(
            """
            SELECT discord_id, attendance_coins, voice_accumulated_minutes 
            FROM users 
            WHERE attendance_coins > 0 OR voice_accumulated_minutes > 0
            ORDER BY attendance_coins DESC, voice_accumulated_minutes DESC 
            LIMIT ?
            """,
            (limit,),
        ) as cursor:
            rows = await cursor.fetchall()

        return [
            {
                "discord_id": row[0],
                "attendance_coins": row[1] or 0,
                "voice_accumulated_minutes": row[2] or 0,
            }
            for row in rows
        ]

    async def track_voice_presence(self, bot: discord.Client) -> None:
        """
        Scan all voice channels across all guilds the bot is connected to.
        Checks for voice rules:
        - Must be in a channel with at least 1 non-bot member.
        - Must not be self-muted/deafened or server-muted/deafened.
        Increments active members' voice presence by 1 minute.
        """
        db = await self.db_service.get_db()
        users_updated = False

        for guild in bot.guilds:
            for voice_channel in guild.voice_channels:
                # Find non-bot members
                members = [m for m in voice_channel.members if not m.bot]
                if len(members) < 1:
                    continue

                for member in members:
                    v_state = member.voice
                    if not v_state:
                        continue

                    # Rule check: ignore muted or deafened users
                    is_muted = v_state.self_mute or v_state.mute
                    is_deafened = v_state.self_deaf or v_state.deaf
                    if is_muted or is_deafened:
                        continue

                    discord_id = str(member.id)
                    user_data = await self.get_user_coins(discord_id)

                    current_coins = user_data["attendance_coins"]
                    new_coins = current_coins + 1

                    await db.execute(
                        """
                        UPDATE users 
                        SET attendance_coins = ?, voice_accumulated_minutes = 0 
                        WHERE discord_id = ?
                        """,
                        (new_coins, discord_id),
                    )
                    users_updated = True

                    logger.info(
                        f"User {member.display_name} ({discord_id}) earned 1 coin from voice presence!"
                    )

        if users_updated:
            await db.commit()
            # Update the persistent leaderboard
            await self.update_leaderboard_channel(bot)

    async def update_leaderboard_channel(self, bot: discord.Client) -> None:
        """
        Builds the current top leaderboard Embed and edits/creates the message in the leaderboard channel.
        Uses auto-discovery to reuse the existing leaderboard message.
        """
        channel_id = settings.LB_CHANNEL_ID or settings.LEADERBOARD_CHANNEL_ID
        if not channel_id:
            logger.warning(
                "Neither LB_CHANNEL_ID nor LEADERBOARD_CHANNEL_ID is configured in settings. Skipping leaderboard update."
            )
            return

        channel = bot.get_channel(channel_id)
        if not channel:
            # Fetch channel asynchronously if it wasn't in cache
            try:
                channel = await bot.fetch_channel(channel_id)
            except Exception as e:
                logger.error(f"Failed to fetch leaderboard channel {channel_id}: {e}")
                return

        if not isinstance(channel, discord.TextChannel):
            logger.error("Leaderboard channel must be a text channel.")
            return

        # Fetch top users
        top_users = await self.get_leaderboard_data(limit=10)

        # Build a hash to see if data has changed
        data_signature = "|".join(
            [f"{u['discord_id']}:{u['attendance_coins']}" for u in top_users]
        )
        data_hash = hashlib.md5(data_signature.encode("utf-8")).hexdigest()

        if self._last_leaderboard_hash == data_hash:
            # Content hasn't changed, skip editing to avoid rate limits
            return

        # Build Embed
        embed = discord.Embed(
            title="🏆 SECRETARY KIM ATTENDANCE LEADERBOARD",
            description="Members earn **1 Coin** for every **minute** active in voice rooms.\n*(Muted or deafened states are excluded)*\n",
            color=0xFFD700,  # Gold
        )

        leaderboard_content = ""
        medals = {0: "🥇", 1: "🥈", 2: "🥉"}

        if not top_users:
            leaderboard_content = "*No attendance data yet. Join a voice room with friends to start earning!*"
        else:
            for idx, user_data in enumerate(top_users):
                medal = medals.get(idx, f"`#{idx + 1:02d}`")
                user_mention = f"<@{user_data['discord_id']}>"
                coins = user_data["attendance_coins"]
                leaderboard_content += f"{medal} {user_mention} — **{coins}** Coins\n"

        embed.add_field(
            name="✨ Top Voice Attendees", value=leaderboard_content, inline=False
        )

        # Local timezone (GMT+7) for last updated timestamp
        tz = datetime.timezone(datetime.timedelta(hours=7))
        now = datetime.datetime.now(tz)
        embed.set_footer(
            text=f"Last updated: {now.strftime('%d/%m/%Y %H:%M:%S')} (GMT+7)"
        )

        # Differentiate between editing and sending new
        leaderboard_msg = None

        if self._leaderboard_msg_id:
            try:
                leaderboard_msg = await channel.fetch_message(self._leaderboard_msg_id)
            except discord.NotFound:
                self._leaderboard_msg_id = None
            except Exception as e:
                logger.warning(f"Error fetching cached leaderboard message: {e}")

        # If not found in cache, scan last 100 messages for auto-discovery
        if not leaderboard_msg:
            try:
                async for msg in channel.history(limit=100):
                    if msg.author.id == bot.user.id and msg.embeds:
                        if "ATTENDANCE LEADERBOARD" in str(msg.embeds[0].title):
                            leaderboard_msg = msg
                            self._leaderboard_msg_id = msg.id
                            break
            except Exception as e:
                logger.error(f"Error scanning channel history: {e}")

        try:
            if leaderboard_msg:
                await leaderboard_msg.edit(embed=embed)
            else:
                new_msg = await channel.send(embed=embed)
                self._leaderboard_msg_id = new_msg.id
            self._last_leaderboard_hash = data_hash
        except Exception as e:
            logger.error(f"Failed to post/edit leaderboard message: {e}")
