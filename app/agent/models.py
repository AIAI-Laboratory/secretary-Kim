from typing import Any

from pydantic import BaseModel, Field


class AgentRequest(BaseModel):
    """
    Request data sent to the Agent from the presentation layer (e.g. Discord Bot, Webhook, etc.).
    """

    model_config = {"arbitrary_types_allowed": True}

    user_id: str = Field(description="ID of the user sending the request")
    user_name: str = Field(description="Display name of the user")
    guild_id: str | None = Field(None, description="Discord server ID (if any)")
    channel_id: str = Field(
        description="ID of the chat channel where the request was sent"
    )
    content: str = Field(description="Text content of the natural language request")

    # Original objects from Discord (if deeper processing is needed at the Skill layer)
    discord_guild: Any | None = Field(None, description="discord.Guild object")
    discord_member: Any | None = Field(None, description="discord.Member object")
    discord_interaction: Any | None = Field(
        None, description="discord.Interaction object"
    )


class SkillContext(BaseModel):
    """
    Context provided to Skills during execution.
    Includes environment info, user list, voice channels, etc.
    """

    model_config = {"arbitrary_types_allowed": True}

    guild_id: str | None = None
    channel_id: str
    user_id: str
    user_name: str

    # Server-specific context for tasks like member analysis
    server_members: dict[str, str] = Field(
        default_factory=dict, description="Map of Discord ID -> Display Name"
    )
    voice_channels: dict[str, str] = Field(
        default_factory=dict, description="Map of Channel ID -> Voice Channel Name"
    )
    current_time_info: str = Field(
        "", description="Current time info in human-readable format"
    )

    # Reference to Discord objects if direct API interaction is needed
    discord_guild: Any | None = None
    discord_member: Any | None = None
    discord_interaction: Any | None = None


class SkillResult(BaseModel):
    """
    Result returned after a Skill finishes executing an action/tool.
    """

    model_config = {"arbitrary_types_allowed": True}

    success: bool = Field(
        description="True if execution is successful, False if failed"
    )
    message: str = Field(description="Text feedback message for the user")
    embed: Any | None = Field(
        None, description="Accompanying Discord Embed object (if any)"
    )
    view: Any | None = Field(
        None,
        description="Accompanying Discord UI View (buttons, dropdowns, etc.) (if any)",
    )
    needs_confirmation: bool = Field(
        False,
        description="True if this action requires user confirmation (approve/reject)",
    )
    data: dict[str, Any] | None = Field(
        None, description="Additional raw data returned to Agent Core"
    )


class AgentResponse(BaseModel):
    """
    Final response from Agent Core back to the Presentation Layer.
    """

    model_config = {"arbitrary_types_allowed": True}

    content: str | None = Field(None, description="Returned chat content")
    embed: Any | None = Field(None, description="Accompanying embed")
    view: Any | None = Field(None, description="Accompanying button UI")
    skill_used: str | None = Field(
        None, description="Name of the skill that processed this request"
    )
