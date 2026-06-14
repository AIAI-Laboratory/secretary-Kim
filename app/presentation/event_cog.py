import discord
from discord.ext import commands
from discord import app_commands
import datetime
from app.domain.models.event import ProposedAction
from app.core.logger import get_logger

logger = get_logger(__name__)

def create_proposed_embed(action: ProposedAction, requester: discord.Member) -> discord.Embed:
    """Tạo một Discord Embed hiển thị chi tiết của Proposed Action."""
    embed = discord.Embed(
        title="📋 Bản Nháp Event (Proposed Action)",
        description=(
            "Thư Ký Kim đã dịch câu lệnh tự nhiên của bạn thành thông tin chi tiết dưới đây.\n"
            "Vui lòng nhấn **Approve** để phê duyệt tạo event, hoặc **Reject** để hủy, **Edit** để chỉnh sửa."
        ),
        color=0xFEE75C  # Màu vàng cảnh báo nháp
    )
    
    embed.add_field(name="📌 Tên Event/Task", value=action.event_name, inline=False)
    embed.add_field(name="📝 Mô tả", value=action.description or "Không có mô tả", inline=False)
    
    assignee_str = f"<@{action.assignee_id}>" if action.assignee_id else (action.assignee_name or "Chưa gán")
    embed.add_field(name="👤 Người thực hiện (Assignee)", value=assignee_str, inline=True)
    
    # Định dạng mốc thời gian hiển thị dưới dạng Discord timestamp
    start_str = "Không xác định"
    if action.scheduled_start_time:
        try:
            dt = datetime.datetime.fromisoformat(action.scheduled_start_time)
            timestamp = int(dt.timestamp())
            start_str = f"<t:{timestamp}:F> (<t:{timestamp}:R>)"
        except Exception:
            start_str = action.scheduled_start_time
            
    embed.add_field(name="⏰ Thời gian bắt đầu", value=start_str, inline=True)
    location_val = f"🔊 Kênh thoại: <#{action.channel_id}>" if action.channel_id else (action.location or "Discord Server")
    embed.add_field(name="📍 Địa điểm", value=location_val, inline=True)
    
    embed.set_footer(text=f"Yêu cầu bởi {requester.display_name}")
    return embed


class EditEventModal(discord.ui.Modal):
    """Modal cho phép chỉnh sửa thông tin bản nháp trước khi phê duyệt."""
    def __init__(self, parent_view: 'ProposedActionView'):
        super().__init__(title="Chỉnh sửa thông tin Event")
        self.parent_view = parent_view
        self.action = parent_view.action

        self.name_input = discord.ui.TextInput(
            label="Tên Event/Task",
            default=self.action.event_name,
            placeholder="Nhập tên event/task",
            required=True
        )
        self.add_item(self.name_input)

        self.desc_input = discord.ui.TextInput(
            label="Mô tả",
            style=discord.TextStyle.paragraph,
            default=self.action.description or "",
            placeholder="Mô tả công việc, deadline, phân công...",
            required=False
        )
        self.add_item(self.desc_input)

        self.assignee_input = discord.ui.TextInput(
            label="Người thực hiện (ID, @Mention hoặc Tên)",
            default=self.action.assignee_id or self.action.assignee_name or "",
            placeholder="ID, tag user, hoặc để trống",
            required=False
        )
        self.add_item(self.assignee_input)

        self.time_input = discord.ui.TextInput(
            label="Thời gian bắt đầu (ISO 8601)",
            default=self.action.scheduled_start_time or "",
            placeholder="Ví dụ: 2026-06-19T17:00:00+07:00",
            required=True
        )
        self.add_item(self.time_input)

        self.loc_input = discord.ui.TextInput(
            label="Địa điểm",
            default=self.action.location or "Discord Server",
            placeholder="Địa điểm tổ chức event",
            required=False
        )
        self.add_item(self.loc_input)

    async def on_submit(self, interaction: discord.Interaction):
        # Validate định dạng thời gian
        try:
            datetime.datetime.fromisoformat(self.time_input.value)
        except ValueError:
            await interaction.response.send_message(
                "❌ Định dạng thời gian không hợp lệ. Vui lòng sử dụng định dạng ISO 8601 (ví dụ: `2026-06-19T17:00:00+07:00`).",
                ephemeral=True
            )
            return

        # Cập nhật thông tin event
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
                voice_chan = discord.utils.get(interaction.guild.voice_channels, id=int(clean_chan_id))
            if not voice_chan:
                # Tìm phòng thoại theo tên (không phân biệt chữ hoa thường)
                voice_chan = discord.utils.find(lambda c: c.name.lower() == loc_val.lower(), interaction.guild.voice_channels)
            
            if voice_chan:
                self.action.channel_id = str(voice_chan.id)
                self.action.channel_name = voice_chan.name
                self.action.location = None

        # Phân tích người được gán (Assignee)
        assignee_val = self.assignee_input.value.strip()
        if assignee_val:
            # Trích xuất ID dạng số nếu là Mention hoặc ID trực tiếp
            clean_id = "".join(filter(str.isdigit, assignee_val))
            if clean_id:
                self.action.assignee_id = clean_id
                member = interaction.guild.get_member(int(clean_id)) if interaction.guild else None
                if member:
                    self.action.assignee_name = member.display_name
                else:
                    self.action.assignee_name = f"User ID: {clean_id}"
            else:
                # Tìm kiếm theo tên trong server
                member = None
                if interaction.guild:
                    member = discord.utils.get(interaction.guild.members, name=assignee_val)
                    if not member:
                        member = discord.utils.get(interaction.guild.members, display_name=assignee_val)
                
                if member:
                    self.action.assignee_id = str(member.id)
                    self.action.assignee_name = member.display_name
                else:
                    self.action.assignee_id = None
                    self.action.assignee_name = assignee_val
        else:
            self.action.assignee_id = None
            self.action.assignee_name = None

        # Cập nhật lại giao diện embed
        embed = create_proposed_embed(self.action, self.parent_view.requester)
        await interaction.response.edit_message(embed=embed, view=self.parent_view)


class ProposedActionView(discord.ui.View):
    """View chứa các nút bấm Approve, Reject, Edit cho bản nháp."""
    def __init__(self, action: ProposedAction, requester: discord.Member, bot: commands.Bot):
        super().__init__(timeout=600)  # Hạn chế timeout trong 10 phút
        self.action = action
        self.requester = requester
        self.bot = bot

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # Chỉ người yêu cầu ban đầu hoặc Quản trị viên/Người quản lý event mới có thể bấm nút
        is_admin = interaction.user.guild_permissions.administrator or interaction.user.guild_permissions.manage_events
        if interaction.user.id == self.requester.id or is_admin:
            return True
        await interaction.response.send_message("❌ Bạn không được phân quyền để phê duyệt bản nháp này.", ephemeral=True)
        return False

    @discord.ui.button(label="Approve", style=discord.ButtonStyle.green, emoji="✅")
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        
        guild = interaction.guild
        if not guild:
            await interaction.followup.send("❌ Chỉ có thể chạy lệnh này trong server Discord.")
            return

        try:
            # Phân tích thời gian bắt đầu
            start_time = datetime.datetime.fromisoformat(self.action.scheduled_start_time)
            
            # Đảm bảo thời gian bắt đầu có múi giờ
            if start_time.tzinfo is None:
                tz = datetime.timezone(datetime.timedelta(hours=7))
                start_time = start_time.replace(tzinfo=tz)
                
            # Discord yêu cầu thời gian bắt đầu của event phải ở tương lai
            now = datetime.datetime.now(datetime.timezone.utc)
            if start_time < now:
                # Tự động đẩy lên thời điểm hiện tại + 5 phút để tránh lỗi Discord
                start_time = now + datetime.timedelta(minutes=5)
                logger.info(f"Thời gian bắt đầu ở quá khứ. Đã cập nhật thành tương lai: {start_time}")
            
            # Tính thời gian kết thúc (Mặc định 1 giờ sau khi bắt đầu)
            end_time = None
            if self.action.scheduled_end_time:
                try:
                    end_time = datetime.datetime.fromisoformat(self.action.scheduled_end_time)
                    if end_time.tzinfo is None:
                        tz = datetime.timezone(datetime.timedelta(hours=7))
                        end_time = end_time.replace(tzinfo=tz)
                    if end_time <= start_time:
                        end_time = start_time + datetime.timedelta(hours=1)
                except Exception:
                    pass
            
            if not end_time:
                end_time = start_time + datetime.timedelta(hours=1)

            # Thực hiện tạo Event trên Discord Guild
            voice_channel = None
            if self.action.channel_id:
                try:
                    voice_channel = guild.get_channel(int(self.action.channel_id))
                except Exception:
                    pass

            if voice_channel:
                event = await guild.create_scheduled_event(
                    name=self.action.event_name,
                    description=self.action.description or "",
                    start_time=start_time,
                    end_time=end_time,
                    entity_type=discord.EntityType.voice,
                    channel=voice_channel,
                    privacy_level=discord.PrivacyLevel.guild_only
                )
            else:
                event = await guild.create_scheduled_event(
                    name=self.action.event_name,
                    description=self.action.description or "",
                    start_time=start_time,
                    end_time=end_time,
                    entity_type=discord.EntityType.external,
                    location=self.action.location or "Discord Server",
                    privacy_level=discord.PrivacyLevel.guild_only
                )

            # Cập nhật thông báo đã tạo thành công, vô hiệu hóa các nút bấm
            embed = discord.Embed(
                title="✅ Event Đã Được Phê Duyệt & Tạo Thành Công",
                description=f"Event đã được tạo thành công trên server bởi {interaction.user.mention}.",
                color=0x57F287  # Xanh lục
            )
            embed.add_field(name="📌 Tên Event/Task", value=event.name, inline=False)
            embed.add_field(name="⏰ Bắt đầu", value=f"<t:{int(event.start_time.timestamp())}:F>", inline=True)
            location_display = f"<#{event.channel.id}>" if event.channel else (event.location or "Discord Server")
            embed.add_field(name="📍 Địa điểm", value=location_display, inline=True)
            embed.add_field(name="🔗 Chi tiết Event", value=f"[Bấm để xem Event trên server]({event.url})", inline=False)
            
            for child in self.children:
                child.disabled = True
                
            await interaction.edit_original_response(embed=embed, view=self)

            # Gửi tin nhắn ping @everyone thông báo về Event mới
            announcement_location = f"<#{event.channel.id}>" if event.channel else (event.location or "Discord Server")
            announcement = (
                f"@everyone 📢 **THÔNG BÁO EVENT MỚI!**\n"
                f"Một event/task vừa được phê duyệt và khởi tạo:\n"
                f"📌 **Tên:** {event.name}\n"
                f"⏰ **Thời gian:** <t:{int(event.start_time.timestamp())}:F>\n"
                f"👤 **Người thực hiện:** {f'<@{self.action.assignee_id}>' if self.action.assignee_id else (self.action.assignee_name or 'Chưa gán')}\n"
                f"📍 **Địa điểm:** {announcement_location}\n"
                f"🔗 **Link chi tiết:** {event.url}"
            )
            await interaction.channel.send(content=announcement)

        except discord.Forbidden:
            logger.error("Lỗi phân quyền khi tạo Discord Guild Scheduled Event.")
            await interaction.followup.send(
                "❌ Thư Ký Kim không có quyền tạo Event. Vui lòng cấp quyền `Quản lý Event` (Manage Events) cho bot.",
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Lỗi khi phê duyệt tạo event: {e}", exc_info=True)
            await interaction.followup.send(f"❌ Đã xảy ra lỗi khi tạo event: {e}", ephemeral=True)

    @discord.ui.button(label="Reject", style=discord.ButtonStyle.red, emoji="✖️")
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        
        embed = discord.Embed(
            title="❌ Bản Nháp Bị Hủy Bỏ",
            description=f"Bản nháp event này đã bị hủy bởi {interaction.user.mention}.",
            color=0xED4245  # Đỏ
        )
        
        for child in self.children:
            child.disabled = True
            
        await interaction.edit_original_response(embed=embed, view=self)
        await interaction.channel.send(f"❌ Đã hủy yêu cầu tạo event: **{self.action.event_name}**.")

    @discord.ui.button(label="Edit", style=discord.ButtonStyle.secondary, emoji="✏️")
    async def edit(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = EditEventModal(self)
        await interaction.response.send_modal(modal)


class EventCog(commands.Cog):
    """Cog xử lý tạo Discord Event từ ngôn ngữ tự nhiên sử dụng AI Agent."""
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="kim", description="Yêu cầu Thư Ký Kim lập event/task bằng ngôn ngữ tự nhiên")
    @app_commands.describe(request="Nội dung yêu cầu (ví dụ: Tạo một task thiết kế giao diện mobile hạn chót thứ sáu này gán cho @Duy)")
    async def kim(self, interaction: discord.Interaction, request: str):
        # Tránh lỗi Discord timeout sau 3 giây bằng defer()
        await interaction.response.defer()
        
        # Lấy thông tin thời gian hiện tại ở múi giờ GMT+7 (Việt Nam)
        tz = datetime.timezone(datetime.timedelta(hours=7))
        now = datetime.datetime.now(tz)
        days = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"]
        weekday = days[now.weekday()]
        current_time_info = f"Hôm nay là {weekday}, ngày {now.strftime('%d/%m/%Y')}. Lúc này là {now.strftime('%H:%M:%S')} (UTC+7)."
        
        # Thu thập danh sách user trong server dạng {id: display_name}
        user_list = {}
        channel_list = {}
        if interaction.guild:
            try:
                # Fetch members thay vì dùng cache guild.members để đảm bảo đầy đủ
                async for member in interaction.guild.fetch_members(limit=200):
                    if not member.bot:
                        user_list[str(member.id)] = member.display_name
            except Exception as e:
                logger.warning(f"Lỗi khi fetch members: {e}. Sử dụng cache rỗng.")
            
            try:
                # Thu thập danh sách phòng thoại (voice channels)
                for channel in interaction.guild.voice_channels:
                    channel_list[str(channel.id)] = channel.name
            except Exception as e:
                logger.warning(f"Lỗi khi lấy danh sách phòng thoại: {e}")

        try:
            # Gọi LLM AI Agent phân tích và chuyển đổi thành đề xuất hành động
            action = await self.bot.event_agent_service.parse_prompt(
                prompt=request,
                user_list=user_list,
                channel_list=channel_list,
                current_time_info=current_time_info
            )
            
            # Kiểm tra xem AI có hiểu ý người dùng không
            if not action.is_valid_event or not action.event_name or not action.scheduled_start_time:
                await interaction.followup.send("Kim chưa hiểu rõ ý")
                return

            # Gửi đề xuất kèm view chứa các nút tương tác
            embed = create_proposed_embed(action, interaction.user)
            view = ProposedActionView(action, interaction.user, self.bot)
            await interaction.followup.send(embed=embed, view=view)

        except Exception as e:
            logger.error(f"Lỗi hệ thống khi xử lý câu lệnh /kim: {e}", exc_info=True)
            await interaction.followup.send("❌ Hệ thống gặp lỗi khi xử lý yêu cầu. Vui lòng thử lại sau.", ephemeral=True)
