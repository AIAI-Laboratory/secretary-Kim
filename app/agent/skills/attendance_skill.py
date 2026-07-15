from typing import Any, Dict, List
import discord
from google.genai import types
from app.agent.skills.base import BaseSkill
from app.agent.models import SkillContext, SkillResult
from app.services.attendance import AttendanceService


class AttendanceSkill(BaseSkill):
    """
    Skill to manage attendance coins and display the voice room activity leaderboard.
    """

    def __init__(self, attendance_service: AttendanceService):
        self.attendance_service = attendance_service

    @property
    def name(self) -> str:
        return "attendance"

    @property
    def description(self) -> str:
        return "Checks attendance coin balance and displays the voice room attendance leaderboard."

    def get_function_declarations(self) -> List[types.FunctionDeclaration]:
        return [
            types.FunctionDeclaration(
                name="check_my_attendance_coins",
                description="Check the current user's attendance coins balance and accumulated minutes.",
                parameters={
                    "type": "OBJECT",
                    "properties": {},
                },
            ),
            types.FunctionDeclaration(
                name="view_attendance_leaderboard",
                description="View the top voice attendance leaderboard in chat.",
                parameters={
                    "type": "OBJECT",
                    "properties": {
                        "limit": {
                            "type": "INTEGER",
                            "description": "Max number of users to show (default: 10, max: 25)",
                        }
                    },
                },
            ),
        ]

    async def execute(
        self, function_name: str, args: Dict[str, Any], context: SkillContext
    ) -> SkillResult:
        if function_name == "check_my_attendance_coins":
            user_id = context.user_id
            user_name = context.user_name

            data = await self.attendance_service.get_user_coins(user_id)
            coins = data["attendance_coins"]

            embed = discord.Embed(
                title=f"🪙 {user_name}'s Attendance Card",
                description="Check your presence status and coins earned below.",
                color=0xFFD700,  # Gold
            )
            embed.add_field(
                name="Coins Earned", value=f"**{coins}** Coins", inline=True
            )
            embed.set_footer(text="Join voice room with others to earn more!")

            return SkillResult(
                success=True,
                message=f"Here is your attendance card, {user_name}:",
                embed=embed,
            )

        elif function_name == "view_attendance_leaderboard":
            limit = args.get("limit") or 10
            limit = min(max(1, limit), 25)

            top_users = await self.attendance_service.get_leaderboard_data(limit=limit)

            embed = discord.Embed(
                title="🏆 Voice Attendance Leaderboard",
                description=f"Top {limit} attendees in voice rooms.",
                color=0xFFD700,
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
                    leaderboard_content += (
                        f"{medal} {user_mention} — **{coins}** Coins\n"
                    )

            embed.add_field(name="✨ Rankings", value=leaderboard_content, inline=False)
            return SkillResult(
                success=True,
                message="Here is the attendance leaderboard:",
                embed=embed,
            )

        return SkillResult(
            success=False,
            message=f"Action '{function_name}' is not supported in AttendanceSkill.",
        )
