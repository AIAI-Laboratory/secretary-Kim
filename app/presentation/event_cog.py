import discord
from discord.ext import commands
from discord import app_commands
import datetime
from app.domain.models.event import ProposedAction
from app.agent.models import AgentRequest
from app.core.logger import get_logger

logger = get_logger(__name__)


def create_proposed_embed(
    action: ProposedAction, requester: discord.Member
) -> discord.Embed:
    """Create a Discord Embed displaying the details of the Proposed Action."""
    embed = discord.Embed(
        title="📋 Event Draft (Proposed Action)",
        description=(
            "Secretary Kim has translated your natural language command into the details below.\n"
            "Please click **Approve** to authorize event creation, **Reject** to cancel, or **Edit** to modify."
        ),
        color=0xFEE75C,  # Yellow warning color for draft
    )

    embed.add_field(name="📌 Event/Task Title", value=action.event_name, inline=False)
    embed.add_field(
        name="📝 Description",
        value=action.description or "No description",
        inline=False,
    )

    assignee_str = (
        f"<@{action.assignee_id}>"
        if action.assignee_id
        else (action.assignee_name or "Unassigned")
    )
    embed.add_field(name="👤 Assignee", value=assignee_str, inline=True)

    # Format time display as a Discord timestamp
    start_str = "Unknown"
    if action.scheduled_start_time:
        try:
            dt = datetime.datetime.fromisoformat(action.scheduled_start_time)
            timestamp = int(dt.timestamp())
            start_str = f"<t:{timestamp}:F> (<t:{timestamp}:R>)"
        except Exception:
            start_str = action.scheduled_start_time

    embed.add_field(name="⏰ Start Time", value=start_str, inline=True)
    location_val = (
        f"🔊 Voice Channel: <#{action.channel_id}>"
        if action.channel_id
        else (action.location or "Discord Server")
    )
    embed.add_field(name="📍 Location", value=location_val, inline=True)

    embed.set_footer(text=f"Requested by {requester.display_name}")
    return embed


class EditEventModal(discord.ui.Modal):
    """Modal to edit the draft details before approval."""

    def __init__(self, parent_view: "ProposedActionView"):
        super().__init__(title="Edit Event Information")
        self.parent_view = parent_view
        self.action = parent_view.action

        self.name_input = discord.ui.TextInput(
            label="Event/Task Title",
            default=self.action.event_name,
            placeholder="Enter event/task title",
            required=True,
        )
        self.add_item(self.name_input)

        self.desc_input = discord.ui.TextInput(
            label="Description",
            style=discord.TextStyle.paragraph,
            default=self.action.description or "",
            placeholder="Job description, deadline, assignments...",
            required=False,
        )
        self.add_item(self.desc_input)

        self.assignee_input = discord.ui.TextInput(
            label="Assignee (ID, @Mention, or Name)",
            default=self.action.assignee_id or self.action.assignee_name or "",
            placeholder="ID, user tag, or leave blank",
            required=False,
        )
        self.add_item(self.assignee_input)

        self.time_input = discord.ui.TextInput(
            label="Start Time (ISO 8601)",
            default=self.action.scheduled_start_time or "",
            placeholder="Example: 2026-06-19T17:00:00+07:00",
            required=True,
        )
        self.add_item(self.time_input)

        self.loc_input = discord.ui.TextInput(
            label="Location",
            default=self.action.location or "Discord Server",
            placeholder="Location where the event is held",
            required=False,
        )
        self.add_item(self.loc_input)

    async def on_submit(self, interaction: discord.Interaction):
        # Validate time format
        try:
            datetime.datetime.fromisoformat(self.time_input.value)
        except ValueError:
            await interaction.response.send_message(
                "❌ Invalid time format. Please use ISO 8601 format (e.g. `2026-06-19T17:00:00+07:00`).",
                ephemeral=True,
            )
            return

        # Update event info
        self.action.event_name = self.name_input.value
        self.action.description = self.desc_input.value
        self.action.scheduled_start_time = self.time_input.value

        loc_val = self.loc_input.value.strip()
        self.action.channel_id = None
        self.action.channel_name = None
        self.action.location = loc_val or "Discord Server"

        if loc_val and interaction.guild:
            clean_chan_id = "".join(filter(str.isdigit, loc_val))
            voice_chan = None
            if clean_chan_id:
                voice_chan = discord.utils.get(
                    interaction.guild.voice_channels, id=int(clean_chan_id)
                )
            if not voice_chan:
                # Find voice room by name (case-insensitive)
                voice_chan = discord.utils.find(
                    lambda c: c.name.lower() == loc_val.lower(),
                    interaction.guild.voice_channels,
                )

            if voice_chan:
                self.action.channel_id = str(voice_chan.id)
                self.action.channel_name = voice_chan.name
                self.action.location = None

        # Analyze assignee
        assignee_val = self.assignee_input.value.strip()
        if assignee_val:
            # Extract numeric ID if mention or direct ID
            clean_id = "".join(filter(str.isdigit, assignee_val))
            if clean_id:
                self.action.assignee_id = clean_id
                member = (
                    interaction.guild.get_member(int(clean_id))
                    if interaction.guild
                    else None
                )
                if member:
                    self.action.assignee_name = member.display_name
                else:
                    self.action.assignee_name = f"User ID: {clean_id}"
            else:
                # Search by name in the server
                member = None
                if interaction.guild:
                    member = discord.utils.get(
                        interaction.guild.members, name=assignee_val
                    )
                    if not member:
                        member = discord.utils.get(
                            interaction.guild.members, display_name=assignee_val
                        )

                if member:
                    self.action.assignee_id = str(member.id)
                    self.action.assignee_name = member.display_name
                else:
                    self.action.assignee_id = None
                    self.action.assignee_name = assignee_val
        else:
            self.action.assignee_id = None
            self.action.assignee_name = None

        # Update the embed interface
        embed = create_proposed_embed(self.action, self.parent_view.requester)
        await interaction.response.edit_message(embed=embed, view=self.parent_view)


class ProposedActionView(discord.ui.View):
    """View containing Approve, Reject, and Edit buttons for the draft."""

    def __init__(
        self, action: ProposedAction, requester: discord.Member, bot: commands.Bot
    ):
        super().__init__(timeout=600)  # Timeout after 10 minutes
        self.action = action
        self.requester = requester
        self.bot = bot

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # Only the original requester or Administrator/Event Manager can click buttons
        is_admin = (
            interaction.user.guild_permissions.administrator
            or interaction.user.guild_permissions.manage_events
        )
        if interaction.user.id == self.requester.id or is_admin:
            return True
        await interaction.response.send_message(
            "❌ You are not authorized to approve this draft.", ephemeral=True
        )
        return False

    @discord.ui.button(label="Approve", style=discord.ButtonStyle.green, emoji="✅")
    async def approve(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.defer()

        guild = interaction.guild
        if not guild:
            await interaction.followup.send(
                "❌ This command can only be run within a Discord server."
            )
            return

        try:
            # Parse start time
            start_time = datetime.datetime.fromisoformat(
                self.action.scheduled_start_time
            )

            end_time = None
            if self.action.scheduled_end_time:
                try:
                    end_time = datetime.datetime.fromisoformat(
                        self.action.scheduled_end_time
                    )
                except Exception:
                    pass

            # Call EventService from the business layer to create the event
            event = await self.bot.event_service.create_event(
                guild=guild,
                name=self.action.event_name,
                start_time=start_time,
                end_time=end_time,
                description=self.action.description,
                location=self.action.location,
                channel_id=self.action.channel_id,
            )

            # Update response embed to show success and disable buttons
            embed = discord.Embed(
                title="✅ Event Approved & Successfully Created",
                description=f"Event has been successfully created on the server by {interaction.user.mention}.",
                color=0x57F287,  # Xanh lục
            )
            embed.add_field(name="📌 Event/Task Title", value=event.name, inline=False)
            embed.add_field(
                name="⏰ Start Time",
                value=f"<t:{int(event.start_time.timestamp())}:F>",
                inline=True,
            )
            location_display = (
                f"<#{event.channel.id}>"
                if event.channel
                else (event.location or "Discord Server")
            )
            embed.add_field(name="📍 Location", value=location_display, inline=True)
            embed.add_field(
                name="🔗 Event Details",
                value=f"[Click to view Event on server]({event.url})",
                inline=False,
            )

            for child in self.children:
                child.disabled = True

            await interaction.edit_original_response(embed=embed, view=self)

            # Send announcement with @everyone ping about the new Event
            announcement_location = (
                f"<#{event.channel.id}>"
                if event.channel
                else (event.location or "Discord Server")
            )
            announcement = (
                f"@everyone 📢 **NEW EVENT ANNOUNCEMENT!**\n"
                f"An event/task has just been approved and created:\n"
                f"📌 **Title:** {event.name}\n"
                f"⏰ **Time:** <t:{int(event.start_time.timestamp())}:F>\n"
                f"👤 **Assignee:** {f'<@{self.action.assignee_id}>' if self.action.assignee_id else (self.action.assignee_name or 'Unassigned')}\n"
                f"📍 **Location:** {announcement_location}\n"
                f"🔗 **Detailed Link:** {event.url}"
            )
            await interaction.channel.send(content=announcement)

        except discord.Forbidden:
            logger.error(
                "Permissions error when creating Discord Guild Scheduled Event."
            )
            await interaction.followup.send(
                "❌ Secretary Kim does not have permission to create Events. Please grant the 'Manage Events' permission to the bot.",
                ephemeral=True,
            )
        except Exception as e:
            logger.error(f"Error approving event creation: {e}", exc_info=True)
            await interaction.followup.send(
                f"❌ An error occurred while creating the event: {e}", ephemeral=True
            )

    @discord.ui.button(label="Reject", style=discord.ButtonStyle.red, emoji="✖️")
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()

        embed = discord.Embed(
            title="❌ Draft Cancelled",
            description=f"This event draft was cancelled by {interaction.user.mention}.",
            color=0xED4245,  # Đỏ
        )

        for child in self.children:
            child.disabled = True

        await interaction.edit_original_response(embed=embed, view=self)
        await interaction.channel.send(
            f"❌ Event creation request cancelled: **{self.action.event_name}**."
        )

    @discord.ui.button(label="Edit", style=discord.ButtonStyle.secondary, emoji="✏️")
    async def edit(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = EditEventModal(self)
        await interaction.response.send_modal(modal)


class HelpView(discord.ui.View):
    """View containing interactive pagination buttons for the help menu."""

    def __init__(self, user_id: str):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.current_page = 0

        # Pre-create all embeds
        self.pages = [
            self.create_page1_embed(),
            self.create_page2_embed(),
            self.create_page3_embed(),
        ]
        self._update_button_states()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message(
                "❌ This help menu is only for the user who requested it.",
                ephemeral=True,
            )
            return False
        return True

    def create_page1_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="👾 Pokémon Gacha & Pomodoro Focus",
            description="Level up productivity, earn coins, and raise unique procedural companions!",
            color=0x5865F2,
        )
        embed.add_field(
            name="`/gacha`",
            value=(
                "• **Prerequisites**: Costs **100 Coins**.\n"
                "• **How it works**: Rolls procedural types, rarities, and concept themes. Uses Gemini AI to design the companion and PixelLab to render a custom transparent pixel-art image."
            ),
            inline=False,
        )
        embed.add_field(
            name="`/feed [amount=1]`",
            value=(
                "• **Prerequisites**: Must have an active companion and sufficient coins. **20 Coins per Fruit** (cost: `20 * amount`). `amount` must be a positive integer.\n"
                "• **How it works**: Restores **20 HP per fruit** (up to 100 max) and adds random XP (sum of `amount` rolls of **15-30 XP**). Triggers level-ups at 100 XP.\n"
                "• **Evolution Checkpoints**: Common & Epic rarity pets evolve at **Level 5** (Stage 2), **Level 15** (Stage 3), and **Level 30** (Stage 4 Mega - requires Mega-Capable roll). Only 1 stage can evolve per feed."
            ),
            inline=False,
        )
        embed.add_field(
            name="`/pet-active`",
            value="• **How it works**: Displays the statistics (Level, HP, XP, types, evolution details, description, and pixel art) of your currently active companion.",
            inline=False,
        )
        embed.add_field(
            name="`/pet-list`",
            value="• **How it works**: Lists all Pokémon companions in your collection and displays an interactive dropdown to switch your active companion.",
            inline=False,
        )
        embed.add_field(
            name="`/pomodoro-start [duration=25]`",
            value=(
                "• **Prerequisites**: Must join a voice channel.\n"
                "• **How it works**: Starts a focus timer. Earn **1 Coin per minute** of voice presence.\n"
                "• **Caution**: Leaving voice channel early cancels the session and inflicts health damage on your active companion."
            ),
            inline=False,
        )
        embed.add_field(
            name="`/pomodoro-cancel`",
            value="• **How it works**: Terminates active focus timer. Progress is lost, no coins awarded, and active companion takes health damage.",
            inline=False,
        )
        embed.set_footer(text="Page 1/3 | Secretary Kim Assistant")
        return embed

    def create_page2_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="🎵 Music Player",
            description="Play high-quality audio in your voice channel.",
            color=0x57F287,
        )
        embed.add_field(
            name="`/play <query>`",
            value=(
                "• **Prerequisites**: Must join a voice channel.\n"
                "• **How it works**: Connects bot to your voice channel (or moves it if idle), resolves YouTube URLs/search keywords via `yt-dlp`, prepares direct stream links, and appends them to the queue. Automatically starts playing if queue was empty."
            ),
            inline=False,
        )
        embed.add_field(
            name="`/pause`",
            value="• **Prerequisites**: Audio must be currently playing.\n"
            "• **How it works**: Pauses the active audio playback stream.",
            inline=False,
        )
        embed.add_field(
            name="`/resume`",
            value="• **Prerequisites**: Audio must be currently paused.\n"
            "• **How it works**: Resumes the paused audio playback stream.",
            inline=False,
        )
        embed.add_field(
            name="`/skip`",
            value="• **Prerequisites**: Audio must be currently playing.\n"
            "• **How it works**: Skips the current track and automatically starts playing the next track in the queue.",
            inline=False,
        )
        embed.add_field(
            name="`/stop`",
            value="• **How it works**: Stops playback, clears all tracks in the queue, and resets music state.",
            inline=False,
        )
        embed.add_field(
            name="`/leave`",
            value="• **Prerequisites**: Bot must be in a voice channel.\n"
            "• **How it works**: Disconnects the bot from the voice channel and clears the music queue.",
            inline=False,
        )
        embed.add_field(
            name="`/loop`",
            value="• **Prerequisites**: Audio must be playing.\n"
            "• **How it works**: Toggles repeat mode. If enabled, repeats the current track infinitely.",
            inline=False,
        )
        embed.add_field(
            name="`/queue`",
            value="• **How it works**: Displays details of the currently playing track and lists the next 10 queued tracks.",
            inline=False,
        )
        embed.set_footer(text="Page 2/3 | Secretary Kim Assistant")
        return embed

    def create_page3_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="🤖 Assistant / AI Chat",
            description="Talk to Secretary Kim in natural language to perform complex scheduling and automation.",
            color=0xFEE75C,
        )
        embed.add_field(
            name="`/kim <request>`",
            value=(
                "• **How it works**: Routes natural language requests through Google Gemini Pro. The agent maps inputs against server members/voice channels and triggers actions (e.g. playing music, starting Pomodoros, scheduling meetings).\n"
                "• **HITL (Human-in-the-Loop) Workflow**: For server events and task creations, the bot displays a draft card containing action buttons:\n"
                "  - `✅ Approve`: Confirms and creates the scheduled Discord event, pinging `@everyone`.\n"
                "  - `✖️ Reject`: Deletes the draft event.\n"
                "  - `✏️ Edit`: Opens a form modal to manually override details (Title, Description, Assignee, Start Time, Location).\n\n"
                "**Usage Examples:**\n"
                "• `/kim play some lo-fi tracks`\n"
                "• `/kim check the current queue`\n"
                "• `/kim start a pomodoro focus session for 30 minutes`\n"
                "• `/kim schedule a meeting tomorrow at 3 PM called 'Project Sync' in Meeting Room`"
            ),
            inline=False,
        )
        embed.set_footer(text="Page 3/3 | Secretary Kim Assistant")
        return embed

    def _update_button_states(self):
        for idx, child in enumerate(self.children):
            if isinstance(child, discord.ui.Button):
                child.disabled = idx == self.current_page

    @discord.ui.button(label="👾 Gacha & Pomodoro", style=discord.ButtonStyle.primary)
    async def button_gacha(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        self.current_page = 0
        self._update_button_states()
        await interaction.response.edit_message(embed=self.pages[0], view=self)

    @discord.ui.button(label="🎵 Music Player", style=discord.ButtonStyle.success)
    async def button_music(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        self.current_page = 1
        self._update_button_states()
        await interaction.response.edit_message(embed=self.pages[1], view=self)

    @discord.ui.button(label="🤖 AI Assistant", style=discord.ButtonStyle.secondary)
    async def button_ai(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        self.current_page = 2
        self._update_button_states()
        await interaction.response.edit_message(embed=self.pages[2], view=self)


class EventCog(commands.Cog):
    """Cog to handle routing natural language requests through the central AI Agent."""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="kim",
        description="Request Secretary Kim using natural language (play music, schedule meetings, etc.)",
    )
    @app_commands.describe(
        request="Request content (e.g. play a song / schedule a meeting at 3 PM)"
    )
    async def kim(self, interaction: discord.Interaction, request: str):
        # Prevent Discord timeout after 3 seconds
        await interaction.response.defer()

        # Intercept help-like queries for direct response without Gemini API call latency
        clean_req = request.strip().strip("?").lower()
        if clean_req in [
            "help",
            "help me",
            "/help",
            "trợ giúp",
            "cứu",
            "hướng dẫn",
            "show help",
            "show me help",
            "commands",
            "list commands",
        ]:
            view = HelpView(str(interaction.user.id))
            await interaction.followup.send(embed=view.pages[0], view=view)
            return

        # Pack request into AgentRequest to send to core
        request_obj = AgentRequest(
            user_id=str(interaction.user.id),
            user_name=interaction.user.display_name,
            guild_id=str(interaction.guild.id) if interaction.guild else None,
            channel_id=str(interaction.channel.id),
            content=request,
            discord_guild=interaction.guild,
            discord_member=interaction.user,
            discord_interaction=interaction,
        )

        try:
            # Send request to the Agent Core brain
            response = await self.bot.kim_agent.process(request_obj)

            # Send response back to the user
            send_args = {}
            if response.content:
                send_args["content"] = response.content
            if response.embed:
                send_args["embed"] = response.embed
            if response.view:
                send_args["view"] = response.view

            if send_args:
                await interaction.followup.send(**send_args)

        except Exception as e:
            logger.error(
                f"System error when processing /kim command: {e}", exc_info=True
            )
            await interaction.followup.send(
                "❌ The system encountered an error while processing the request. Please try again later.",
                ephemeral=True,
            )

    @app_commands.command(
        name="help",
        description="Show all available slash commands of Secretary Kim with interactive pagination",
    )
    async def help(self, interaction: discord.Interaction):
        view = HelpView(str(interaction.user.id))
        await interaction.response.send_message(embed=view.pages[0], view=view)
