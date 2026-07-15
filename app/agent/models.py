from pydantic import BaseModel, Field
from typing import Optional, Any, Dict


class AgentRequest(BaseModel):
    """
    Request data sent to the Agent from the presentation layer (e.g. Discord Bot, Webhook, etc.).
    """

    model_config = {"arbitrary_types_allowed": True}

    user_id: str = Field(description="ID of the user sending the request")
    user_name: str = Field(description="Display name of the user")
    guild_id: Optional[str] = Field(None, description="Discord server ID (if any)")
    channel_id: str = Field(
        description="ID of the chat channel where the request was sent"
    )
    content: str = Field(description="Text content of the natural language request")

    # Original objects from Discord (if deeper processing is needed at the Skill layer)
    discord_guild: Optional[Any] = Field(None, description="discord.Guild object")
    discord_member: Optional[Any] = Field(None, description="discord.Member object")
    discord_interaction: Optional[Any] = Field(
        None, description="discord.Interaction object"
    )


class SkillContext(BaseModel):
    """
    Context provided to Skills during execution.
    Includes environment info, user list, voice channels, etc.
    """

    model_config = {"arbitrary_types_allowed": True}

    guild_id: Optional[str] = None
    channel_id: str
    user_id: str
    user_name: str

    # Server-specific context for tasks like member analysis
    server_members: Dict[str, str] = Field(
        default_factory=dict, description="Map of Discord ID -> Display Name"
    )
    voice_channels: Dict[str, str] = Field(
        default_factory=dict, description="Map of Channel ID -> Voice Channel Name"
    )
    current_time_info: str = Field(
        "", description="Current time info in human-readable format"
    )

    # Reference to Discord objects if direct API interaction is needed
    discord_guild: Optional[Any] = None
    discord_member: Optional[Any] = None
    discord_interaction: Optional[Any] = None


class SkillResult(BaseModel):
    """
    Result returned after a Skill finishes executing an action/tool.
    """

    model_config = {"arbitrary_types_allowed": True}

    success: bool = Field(
        description="True if execution is successful, False if failed"
    )
    message: str = Field(description="Text feedback message for the user")
    embed: Optional[Any] = Field(
        None, description="Accompanying Discord Embed object (if any)"
    )
    view: Optional[Any] = Field(
        None,
        description="Accompanying Discord UI View (buttons, dropdowns, etc.) (if any)",
    )
    needs_confirmation: bool = Field(
        False,
        description="True if this action requires user confirmation (approve/reject)",
    )
    data: Optional[Dict[str, Any]] = Field(
        None, description="Additional raw data returned to Agent Core"
    )


class AgentResponse(BaseModel):
    """
    Final response from Agent Core back to the Presentation Layer.
    """

    model_config = {"arbitrary_types_allowed": True}

    content: Optional[str] = Field(None, description="Returned chat content")
    embed: Optional[Any] = Field(None, description="Accompanying embed")
    view: Optional[Any] = Field(None, description="Accompanying button UI")
    skill_used: Optional[str] = Field(
        None, description="Name of the skill that processed this request"
    )
