from pydantic import BaseModel, Field
from typing import Optional


class ProposedAction(BaseModel):
    is_valid_event: bool = Field(
        description="True if the prompt is a request to create a task or event on Discord. False if the model does not understand the request or if it is unrelated."
    )
    event_name: Optional[str] = Field(
        None,
        description="The title/name of the event or task (e.g. 'Thiết kế giao diện mobile')",
    )
    description: Optional[str] = Field(
        None,
        description="A clear description of the task, mentioning the assignee and the deadline.",
    )
    assignee_id: Optional[str] = Field(
        None,
        description="The Discord ID of the assignee from the user list. If no matching user is found, leave as None.",
    )
    assignee_name: Optional[str] = Field(None, description="The name of the assignee.")
    channel_id: Optional[str] = Field(
        None,
        description="The Discord Voice Channel ID matching the requested room name. If no matching channel, leave as None.",
    )
    channel_name: Optional[str] = Field(
        None, description="The name of the matched voice channel."
    )
    scheduled_start_time: Optional[str] = Field(
        None,
        description="ISO 8601 string representing when the event/task starts or is due. Relative dates must be resolved based on the current local time provided.",
    )
    scheduled_end_time: Optional[str] = Field(
        None,
        description="ISO 8601 string representing when the event ends (usually 1 hour after start time, or end of the day, or same as start time).",
    )
    location: Optional[str] = Field(
        "Discord Server", description="Location of the event."
    )
