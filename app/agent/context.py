import datetime
from typing import Any
from app.agent.models import AgentRequest, SkillContext


class ContextEngine:
    """
    Responsible for extracting and normalizing Context from Discord/User requests
    to provide to the LLM or Skills for execution.
    """

    def get_time_context(self) -> str:
        """
        Get the current time information formatted in English.
        """
        tz = datetime.timezone(datetime.timedelta(hours=7))
        now = datetime.datetime.now(tz)
        days = [
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        ]
        weekday = days[now.weekday()]
        return f"Today is {weekday}, {now.strftime('%B %d, %Y')}. The current time is {now.strftime('%H:%M:%S')} (timezone UTC+7)."

    async def build_skill_context(self, request: AgentRequest) -> SkillContext:
        """
        Build a SkillContext object from the original AgentRequest, including scanning Discord server info.
        """
        server_members = {}
        voice_channels = {}

        # If request is sent from a Discord Guild, gather additional context
        guild = request.discord_guild
        if guild:
            # Gather voice channel list
            try:
                for channel in guild.voice_channels:
                    voice_channels[str(channel.id)] = channel.name
            except Exception:
                pass

            # Gather user list (limited by cache or fetch depending on bot design)
            try:
                # In practice, members can be fetched via API or using guild.members cache
                for member in guild.members:
                    if not member.bot:
                        server_members[str(member.id)] = member.display_name
            except Exception:
                pass

        return SkillContext(
            guild_id=request.guild_id,
            channel_id=request.channel_id,
            user_id=request.user_id,
            user_name=request.user_name,
            server_members=server_members,
            voice_channels=voice_channels,
            current_time_info=self.get_time_context(),
            discord_guild=request.discord_guild,
            discord_member=request.discord_member,
            discord_interaction=request.discord_interaction,
        )

    def build_system_instruction(self, skill_descriptions: str) -> str:
        """
        Create the system prompt instructing Gemini to act as an orchestrating Agent.
        """
        time_info = self.get_time_context()
        instruction = (
            "You are Secretary Kim, a smart and friendly personal AI assistant operating on Discord.\n"
            f"Current system time info: {time_info}.\n\n"
            "Your task is to analyze the user's natural language command and invoke the appropriate functions "
            "to fulfill their request.\n"
            "You have the following skills (Skills) available to assist:\n"
            f"{skill_descriptions}\n\n"
            "INSTRUCTIONS:\n"
            "1. If the user wants to perform an action within the capabilities of the skills above, "
            "you MUST call the corresponding function with the exact arguments.\n"
            "2. Resolve relative time phrases (e.g., 'tomorrow', 'this Friday evening') into specific "
            "ISO 8601 date and time based on the provided system time.\n"
            "3. If the user's request is chitchat or unrelated to calling any function, "
            "respond back in a polite, warm, and smart manner."
        )
        return instruction
