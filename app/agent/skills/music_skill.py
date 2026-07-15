import discord
from typing import Any, Dict, List
from google.genai import types
from app.agent.skills.base import BaseSkill
from app.agent.models import SkillContext, SkillResult
from app.services.music import MusicService
from app.core.logger import get_logger

logger = get_logger(__name__)


class MusicSkill(BaseSkill):
    """
    Skill to execute music playback on Discord integrated with MusicService and GuildMusicManager.
    """

    def __init__(self, music_service: MusicService):
        self.music_service = music_service

    @property
    def name(self) -> str:
        return "music"

    @property
    def description(self) -> str:
        return "Controls music: plays music from YouTube, pauses, resumes, skips tracks, and leaves the voice channel."

    def get_function_declarations(self) -> List[types.FunctionDeclaration]:
        return [
            types.FunctionDeclaration(
                name="play_music",
                description="Play a song from YouTube based on a link or search query. The user must be in a voice channel.",
                parameters={
                    "type": "OBJECT",
                    "properties": {
                        "query": {
                            "type": "STRING",
                            "description": "The song title, artist, or YouTube link to play (e.g. 'We Are of the Future')",
                        }
                    },
                    "required": ["query"],
                },
            ),
            types.FunctionDeclaration(
                name="skip_track",
                description="Skip the currently playing song to move to the next song in the queue.",
                parameters={"type": "OBJECT", "properties": {}},
            ),
            types.FunctionDeclaration(
                name="pause_music",
                description="Pause the currently playing song.",
                parameters={"type": "OBJECT", "properties": {}},
            ),
            types.FunctionDeclaration(
                name="resume_music",
                description="Resume playback of the song after it has been paused.",
                parameters={"type": "OBJECT", "properties": {}},
            ),
        ]

    async def execute(
        self, function_name: str, args: Dict[str, Any], context: SkillContext
    ) -> SkillResult:
        # Get discord interaction and bot client
        interaction = context.discord_interaction
        if not interaction:
            return SkillResult(
                success=False,
                message="System error: Discord Interaction not found to process music.",
            )

        bot = interaction.client
        guild = interaction.guild
        member = interaction.user

        if not guild:
            return SkillResult(
                success=False,
                message="This command can only be used in a Discord Server.",
            )

        # Get the music manager for the server
        manager = bot.get_manager(guild.id)

        # Process command: play_music
        if function_name == "play_music":
            query = args.get("query")
            if not query:
                return SkillResult(
                    success=False, message="Please provide a song title or music link."
                )

            # Check if the user is in a voice channel
            if not member.voice or not member.voice.channel:
                return SkillResult(
                    success=False,
                    message="❌ You need to join a voice channel before requesting to play music!",
                )

            user_channel = member.voice.channel

            # Connect bot to the voice channel if not already connected
            voice_client = guild.voice_client
            if not voice_client:
                try:
                    voice_client = await user_channel.connect()
                except Exception as e:
                    logger.error(f"Cannot connect to voice channel: {e}")
                    return SkillResult(
                        success=False,
                        message=f"❌ Cannot connect to voice channel: {e}",
                    )
            elif voice_client.channel != user_channel:
                # Move bot if bot is idle
                if (
                    not voice_client.is_playing()
                    and not voice_client.is_paused()
                    and manager.current is None
                ):
                    try:
                        await voice_client.move_to(user_channel)
                    except Exception as e:
                        logger.warning(f"Cannot move voice channel: {e}")

            # Extract song info from YouTube (runs async via service)
            try:
                info = await self.music_service.extract_info(query)
            except Exception as e:
                logger.error(f"Error extracting video: {e}")
                return SkillResult(
                    success=False,
                    message=f"❌ No results found or an error occurred: {e}",
                )

            track = {
                "title": info.get("title", "No Title"),
                "url": info.get("url"),
                "webpage_url": info.get("webpage_url", query),
                "duration": info.get("duration", 0),
                "thumbnail": info.get("thumbnail"),
                "uploader": info.get("uploader", "Unknown"),
                "requester": member.display_name,
            }

            manager.voice_client = voice_client
            started = await manager.add_track(track, interaction.channel)

            if started:
                return SkillResult(
                    success=True,
                    message=f"🔍 Preparing to play track: **[{track['title']}]({track['webpage_url']})**",
                )
            else:
                queue_pos = len(manager.queue)
                embed = discord.Embed(
                    title="📥 Added to Queue",
                    description=f"**[{track['title']}]({track['webpage_url']})**",
                    color=0xFEE75C,
                )
                if track["thumbnail"]:
                    embed.set_thumbnail(url=track["thumbnail"])
                from app.presentation.discord_bot import format_duration

                embed.add_field(
                    name="⏱️ Duration",
                    value=format_duration(track["duration"]),
                    inline=True,
                )
                embed.add_field(name="👤 Channel", value=track["uploader"], inline=True)
                embed.add_field(
                    name="🔢 Queue Position", value=str(queue_pos), inline=True
                )
                embed.set_footer(text=f"Requested by {track['requester']}")

                return SkillResult(
                    success=True,
                    message=f"Added to queue at position #{queue_pos}",
                    embed=embed,
                )

        # Process command: skip_track
        elif function_name == "skip_track":
            voice_client = guild.voice_client
            if not voice_client or not voice_client.is_playing():
                return SkillResult(
                    success=False,
                    message="❌ There is no song currently playing to skip!",
                )

            voice_client.stop()
            return SkillResult(success=True, message="⏭️ Skipped the current song.")

        # Process command: pause_music
        elif function_name == "pause_music":
            voice_client = guild.voice_client
            if not voice_client or not voice_client.is_playing():
                return SkillResult(
                    success=False, message="❌ There is no song currently playing!"
                )

            voice_client.pause()
            return SkillResult(success=True, message="⏸️ Paused the music.")

        # Process command: resume_music
        elif function_name == "resume_music":
            voice_client = guild.voice_client
            if not voice_client or not voice_client.is_paused():
                return SkillResult(
                    success=False, message="❌ There is no music currently paused!"
                )

            voice_client.resume()
            return SkillResult(success=True, message="▶️ Resumed the music.")

        return SkillResult(
            success=False,
            message=f"Command '{function_name}' is not supported in MusicSkill.",
        )
