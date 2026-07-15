import discord
from discord.ext import commands
from discord import app_commands
import asyncio
from app.services.music import MusicService
from app.services.event import EventService
from app.services.task import TaskService
from app.agent.core import KimAgent
from app.core.logger import get_logger

logger = get_logger(__name__)


def format_duration(seconds: int) -> str:
    """Format seconds to HH:MM:SS or MM:SS time string."""
    if not seconds:
        return "Live / Unknown"
    mins, secs = divmod(seconds, 60)
    hours, mins = divmod(mins, 60)
    if hours > 0:
        return f"{hours:02d}:{mins:02d}:{secs:02d}"
    return f"{mins:02d}:{secs:02d}"


class GuildMusicManager:
    """Manage queue and play music for each distinct Guild (Server)."""

    def __init__(self, bot, guild_id: int):
        self.bot = bot
        self.guild_id = guild_id
        self.queue = []  # Queue containing song info
        self.current = None  # Currently playing song
        self.voice_client = None
        self.text_channel = None  # Chat channel to send music announcements
        self.loop = False  # Loop state of the current song
        self.disconnect_task = (
            None  # Countdown task to automatically leave the voice channel
        )

    async def add_track(self, track: dict, text_channel: discord.TextChannel) -> bool:
        """Add a new song to the queue. Returns True if playing immediately, False if queued."""
        self.text_channel = text_channel
        self.queue.append(track)

        if (
            self.voice_client
            and not self.voice_client.is_playing()
            and not self.voice_client.is_paused()
            and self.current is None
        ):
            await self.play_next()
            return True
        return False

    async def play_next(self):
        """Play the next song in the queue."""
        if not self.voice_client or not self.voice_client.is_connected():
            return

        if len(self.queue) == 0 and not (self.loop and self.current):
            self.current = None
            if self.text_channel:
                embed = discord.Embed(
                    description="🎵 All songs in the queue have been played.",
                    color=0x5865F2,
                )
                await self.text_channel.send(embed=embed)
            return

        # Determine the next song
        if self.loop and self.current:
            track = self.current
        else:
            track = self.queue.pop(0)
            self.current = track

        try:
            # Re-extract direct stream URL from YouTube because YouTube links expire after a few hours
            try:
                info = await self.bot.music_service.extract_info(track["webpage_url"])
                stream_url = info["url"]
            except Exception as e:
                logger.warning(f"Could not refresh stream URL, using original URL: {e}")
                stream_url = track["url"]

            source = discord.FFmpegPCMAudio(
                stream_url, **self.bot.music_service.ffmpeg_options
            )

            def after_playing(error):
                if error:
                    logger.error(
                        f"Error playing music on server {self.guild_id}: {error}"
                    )
                # Schedule play_next() in the event loop from the audio thread
                # Use ensure_future instead of nesting run_coroutine_threadsafe in lambda
                self.bot.loop.call_soon_threadsafe(
                    asyncio.ensure_future, self.play_next()
                )

            self.voice_client.play(source, after=after_playing)

            # Send embed with currently playing song info
            embed = discord.Embed(
                title="▶️ Now Playing",
                description=f"**[{track['title']}]({track['webpage_url']})**",
                color=0x57F287,  # Emerald Green
            )
            if track["thumbnail"]:
                embed.set_thumbnail(url=track["thumbnail"])
            embed.add_field(
                name="⏱️ Duration",
                value=format_duration(track["duration"]),
                inline=True,
            )
            embed.add_field(name="👤 Channel", value=track["uploader"], inline=True)
            embed.set_footer(
                text=f"Requested by {track.get('requester', 'Anonymous')}"
                + (" | 🔁 Loop mode is ON" if self.loop else "")
            )

            if self.text_channel:
                await self.text_channel.send(embed=embed)

        except Exception as e:
            logger.error(f"Error starting music playback: {e}")
            if self.text_channel:
                await self.text_channel.send(
                    f"❌ An error occurred while loading track **{track['title']}**: {e}"
                )
            # Try the next song
            await self.play_next()


class MusicCog(commands.Cog):
    """Cog containing music control commands."""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="play",
        description="Play music from YouTube (enter link or search keywords)",
    )
    @app_commands.describe(query="YouTube video link or search keywords")
    async def play(self, interaction: discord.Interaction, query: str):
        # Check if the user is in a voice channel
        if not interaction.user.voice or not interaction.user.voice.channel:
            embed = discord.Embed(
                description="❌ You need to join a voice channel before using this command!",
                color=0xED4245,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        user_channel = interaction.user.voice.channel
        await interaction.response.defer()

        # Connect or move the bot to the user's voice channel
        voice_client = interaction.guild.voice_client
        if not voice_client:
            try:
                voice_client = await user_channel.connect()
            except Exception as e:
                logger.error(f"Cannot connect to voice channel: {e}")
                embed = discord.Embed(
                    description=f"❌ Cannot connect to voice channel: {e}",
                    color=0xED4245,
                )
                await interaction.followup.send(embed=embed)
                return
        elif voice_client.channel != user_channel:
            # Move if the bot is idle
            manager = self.bot.get_manager(interaction.guild_id)
            if (
                not voice_client.is_playing()
                and not voice_client.is_paused()
                and manager.current is None
            ):
                try:
                    await voice_client.move_to(user_channel)
                except Exception as e:
                    logger.warning(f"Cannot move voice channel: {e}")

        # Search for or extract song info
        try:
            info = await self.bot.music_service.extract_info(query)
        except Exception as e:
            logger.error(f"Error extracting video: {e}")
            embed = discord.Embed(
                description=f"❌ No matching results found or an error occurred: {e}",
                color=0xED4245,
            )
            await interaction.followup.send(embed=embed)
            return

        track = {
            "title": info.get("title", "No Title"),
            "url": info.get("url"),
            "webpage_url": info.get("webpage_url", query),
            "duration": info.get("duration", 0),
            "thumbnail": info.get("thumbnail"),
            "uploader": info.get("uploader", "Unknown"),
            "requester": interaction.user.display_name,
        }

        manager = self.bot.get_manager(interaction.guild_id)
        manager.voice_client = voice_client

        started = await manager.add_track(track, interaction.channel)

        if started:
            embed = discord.Embed(
                description=f"🔍 Preparing to play track: **[{track['title']}]({track['webpage_url']})**",
                color=0x5865F2,
            )
            await interaction.followup.send(embed=embed)
        else:
            queue_pos = len(manager.queue)
            embed = discord.Embed(
                title="📥 Added to Queue",
                description=f"**[{track['title']}]({track['webpage_url']})**",
                color=0xFEE75C,  # Yellow/Orange
            )
            if track["thumbnail"]:
                embed.set_thumbnail(url=track["thumbnail"])
            embed.add_field(
                name="⏱️ Duration",
                value=format_duration(track["duration"]),
                inline=True,
            )
            embed.add_field(name="👤 Channel", value=track["uploader"], inline=True)
            embed.add_field(name="🔢 Queue Position", value=str(queue_pos), inline=True)
            embed.set_footer(text=f"Requested by {track['requester']}")
            await interaction.followup.send(embed=embed)

    @app_commands.command(name="pause", description="Pause the currently playing song")
    async def pause(self, interaction: discord.Interaction):
        voice_client = interaction.guild.voice_client
        if not voice_client or not voice_client.is_playing():
            embed = discord.Embed(
                description="❌ There is no song currently playing!", color=0xED4245
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        voice_client.pause()
        embed = discord.Embed(description="⏸️ Paused the music.", color=0x5865F2)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="resume", description="Resume the currently paused song")
    async def resume(self, interaction: discord.Interaction):
        voice_client = interaction.guild.voice_client
        if not voice_client or not voice_client.is_paused():
            embed = discord.Embed(
                description="❌ There is no music currently paused!", color=0xED4245
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        voice_client.resume()
        embed = discord.Embed(description="▶️ Resumed the music.", color=0x5865F2)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="skip", description="Skip the current song")
    async def skip(self, interaction: discord.Interaction):
        voice_client = interaction.guild.voice_client
        if not voice_client or not voice_client.is_playing():
            embed = discord.Embed(
                description="❌ There is no song currently playing to skip!",
                color=0xED4245,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # Stop the current song. after_playing will automatically play the next song.
        voice_client.stop()
        embed = discord.Embed(
            description="⏭️ Skipped the current song.", color=0x5865F2
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="stop", description="Stop music playback and clear the queue"
    )
    async def stop(self, interaction: discord.Interaction):
        manager = self.bot.get_manager(interaction.guild_id)
        manager.queue.clear()
        manager.current = None
        manager.loop = False

        voice_client = interaction.guild.voice_client
        if voice_client:
            voice_client.stop()

        embed = discord.Embed(
            description="⏹️ Stopped music and cleared the queue.", color=0xED4245
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="leave", description="Leave the current voice channel")
    async def leave(self, interaction: discord.Interaction):
        voice_client = interaction.guild.voice_client
        if not voice_client:
            embed = discord.Embed(
                description="❌ The bot is not currently in any voice channel!",
                color=0xED4245,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        manager = self.bot.get_manager(interaction.guild_id)
        manager.queue.clear()
        manager.current = None
        manager.loop = False

        await voice_client.disconnect()
        embed = discord.Embed(
            description="👋 Disconnected and cleared the queue.", color=0x5865F2
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="loop", description="Toggle loop mode for the current song"
    )
    async def loop(self, interaction: discord.Interaction):
        manager = self.bot.get_manager(interaction.guild_id)
        manager.loop = not manager.loop
        status = "ON" if manager.loop else "OFF"
        embed = discord.Embed(
            description=f"🔁 Loop mode is now **{status}** for the current song.",
            color=0x5865F2,
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="queue", description="Display the current queue")
    async def queue(self, interaction: discord.Interaction):
        manager = self.bot.get_manager(interaction.guild_id)

        if not manager.current and len(manager.queue) == 0:
            embed = discord.Embed(description="🎵 The queue is empty!", color=0x5865F2)
            await interaction.response.send_message(embed=embed)
            return

        embed = discord.Embed(title="🎵 Music Queue", color=0x5865F2)

        if manager.current:
            embed.add_field(
                name="▶️ Now Playing",
                value=f"**[{manager.current['title']}]({manager.current['webpage_url']})** | `{format_duration(manager.current['duration'])}` (Requested by: {manager.current['requester']})",
                inline=False,
            )

        if len(manager.queue) > 0:
            queue_lines = []
            for i, track in enumerate(manager.queue[:10], start=1):
                queue_lines.append(
                    f"`{i}.` **[{track['title']}]({track['webpage_url']})** | `{format_duration(track['duration'])}` (Requested by: {track['requester']})"
                )

            value = "\n".join(queue_lines)
            if len(manager.queue) > 10:
                value += f"\n*and {len(manager.queue) - 10} other songs...*"

            embed.add_field(name="📥 Queue", value=value, inline=False)
        else:
            embed.add_field(
                name="📥 Queue", value="No songs in the queue.", inline=False
            )

        await interaction.response.send_message(embed=embed)

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        voice_client = member.guild.voice_client

        # If bot is no longer in any voice channel or disconnected, cancel the task and clean up the state
        if (
            not voice_client
            or not voice_client.is_connected()
            or not voice_client.channel
        ):
            manager = self.bot.get_manager(member.guild.id)
            if manager.disconnect_task and not manager.disconnect_task.done():
                manager.disconnect_task.cancel()
                manager.disconnect_task = None
            # Clean up the state if the bot itself is disconnected
            if (
                member.id == self.bot.user.id
                and before.channel is not None
                and after.channel is None
            ):
                manager.queue.clear()
                manager.current = None
                manager.loop = False
                logger.info(
                    f"Bot disconnected from voice in guild {member.guild.id}. Cleared music manager state."
                )
            return

        bot_channel = voice_client.channel

        # Only process if the event happens in the voice channel the bot is connected to
        in_before = before.channel == bot_channel
        in_after = after.channel == bot_channel

        if not in_before and not in_after:
            return

        # Count the number of non-bot members in the voice channel
        non_bot_members = [m for m in bot_channel.members if not m.bot]
        manager = self.bot.get_manager(member.guild.id)

        if len(non_bot_members) == 0:
            # If no users are left, start a 10-second countdown to leave
            if not manager.disconnect_task or manager.disconnect_task.done():
                logger.info(
                    f"All members left voice channel {bot_channel.name} in guild {member.guild.id}. Starting 10s leave timer."
                )
                manager.disconnect_task = self.bot.loop.create_task(
                    self.leave_after_delay(member.guild.id, 10)
                )
        else:
            # If a user returns/is in the voice channel, cancel the countdown
            if manager.disconnect_task and not manager.disconnect_task.done():
                logger.info(
                    f"Human found in voice channel {bot_channel.name} in guild {member.guild.id}. Cancelling leave timer."
                )
                manager.disconnect_task.cancel()
                manager.disconnect_task = None

    async def leave_after_delay(self, guild_id: int, delay: int):
        await asyncio.sleep(delay)
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return

        voice_client = guild.voice_client
        if (
            not voice_client
            or not voice_client.is_connected()
            or not voice_client.channel
        ):
            return

        # Re-check the actual number of members before leaving
        non_bot_members = [m for m in voice_client.channel.members if not m.bot]
        if len(non_bot_members) == 0:
            manager = self.bot.get_manager(guild_id)
            manager.queue.clear()
            manager.current = None
            manager.loop = False

            await voice_client.disconnect()
            logger.info(
                f"Bot automatically left voice channel {voice_client.channel.name} in guild {guild_id} due to inactivity (10s empty)."
            )

            if manager.text_channel:
                try:
                    embed = discord.Embed(
                        description="👋 Left the voice channel due to inactivity (10 seconds empty).",
                        color=0x5865F2,
                    )
                    await manager.text_channel.send(embed=embed)
                except Exception as e:
                    logger.warning(f"Could not send auto-leave notification: {e}")


class MusicBot(commands.Bot):
    """Main bot client, handles connection and event dispatching."""

    def __init__(
        self,
        kim_agent: KimAgent,
        music_service: MusicService,
        event_service: EventService,
        task_service: TaskService,
        *args,
        **kwargs,
    ):
        intents = discord.Intents.default()
        intents.voice_states = True

        super().__init__(command_prefix="!", intents=intents, *args, **kwargs)
        self.kim_agent = kim_agent
        self.music_service = music_service
        self.event_service = event_service
        self.task_service = task_service
        self.managers = {}

    def get_manager(self, guild_id: int) -> GuildMusicManager:
        if guild_id not in self.managers:
            self.managers[guild_id] = GuildMusicManager(self, guild_id)
        return self.managers[guild_id]

    async def setup_hook(self):
        # Register music control Cog
        await self.add_cog(MusicCog(self))
        # Register AI event Cog
        from app.presentation.event_cog import EventCog

        await self.add_cog(EventCog(self))
        # Sync slash commands
        await self.tree.sync()
        logger.info("Slash commands synced successfully.")

    async def on_ready(self):
        logger.info(f"Bot logged in successfully as {self.user} (ID: {self.user.id})")
        logger.info("Bot is ready to serve music!")
