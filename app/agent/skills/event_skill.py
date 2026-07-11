from typing import Any, Dict, List
from google.genai import types
from app.agent.skills.base import BaseSkill
from app.agent.models import SkillContext, SkillResult
from app.services.event import EventService
from app.domain.models.event import ProposedAction

class EventSkill(BaseSkill):
    """
    Skill to handle proposed event creation on Discord.
    """
    
    def __init__(self, event_service: EventService):
        self.event_service = event_service

    @property
    def name(self) -> str:
        return "event"

    @property
    def description(self) -> str:
        return "Creates and schedules events (Scheduled Event), meetings, and tasks on Discord."

    def get_function_declarations(self) -> List[types.FunctionDeclaration]:
        return [
            types.FunctionDeclaration(
                name="propose_event",
                description="Propose creating a new event or meeting schedule on the Discord server.",
                parameters={
                    "type": "OBJECT",
                    "properties": {
                        "event_name": {
                            "type": "STRING",
                            "description": "The name or title of the event (e.g. 'Project Kim Technical Meeting')"
                        },
                        "description": {
                            "type": "STRING",
                            "description": "Detailed description of the event content and tasks to be done"
                        },
                        "scheduled_start_time": {
                            "type": "STRING",
                            "description": "Start time in ISO 8601 format (e.g. '2026-07-12T10:00:00+07:00')"
                        },
                        "scheduled_end_time": {
                            "type": "STRING",
                            "description": "End time in ISO 8601 format (if any)"
                        },
                        "assignee_id": {
                            "type": "STRING",
                            "description": "Discord user ID of the person assigned to perform the task (if any)"
                        },
                        "assignee_name": {
                            "type": "STRING",
                            "description": "Display name of the assigned user (if any)"
                        },
                        "location": {
                            "type": "STRING",
                            "description": "Meeting location (leave blank if meeting online in a voice channel)"
                        },
                        "channel_id": {
                            "type": "STRING",
                            "description": "Voice channel ID on Discord if meeting online"
                        }
                    },
                    "required": ["event_name", "scheduled_start_time"]
                }
            )
        ]

    async def execute(self, function_name: str, args: Dict[str, Any], context: SkillContext) -> SkillResult:
        if function_name == "propose_event":
            # Build ProposedAction model from args received from Gemini
            action = ProposedAction(
                is_valid_event=True,
                event_name=args.get("event_name"),
                description=args.get("description"),
                assignee_id=args.get("assignee_id"),
                assignee_name=args.get("assignee_name"),
                channel_id=args.get("channel_id"),
                scheduled_start_time=args.get("scheduled_start_time"),
                scheduled_end_time=args.get("scheduled_end_time"),
                location=args.get("location") or "Discord Server"
            )
            
            # Lazy import UI classes to avoid circular dependencies
            from app.presentation.event_cog import ProposedActionView, create_proposed_embed
            
            # Create embed and approval view at the Skill level
            embed = create_proposed_embed(action, context.discord_member)
            view = ProposedActionView(action, context.discord_member, context.discord_interaction.client)
            
            return SkillResult(
                success=True,
                message="📋 Here is the draft of the proposed event:",
                embed=embed,
                view=view
            )

        return SkillResult(
            success=False,
            message=f"Action '{function_name}' is not supported in EventSkill."
        )
