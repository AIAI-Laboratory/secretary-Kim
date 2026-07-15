import discord
from discord.ext import commands
from discord import app_commands
import asyncio
from app.services.music import MusicService
from app.services.agent.event_management import EventAgentService
from app.services.agent.task_management import TaskManagementAgentService
from app.core.logger import get_logger

logger = get_logger(__name__)


def format_duration(seconds: int) -> str:
    """Định dạng số giây thành chuỗi thời gian HH:MM:SS hoặc MM:SS."""
    if not seconds:
        return "Trực tiếp / Không xác định"
    mins, secs = divmod(seconds, 60)
    hours, mins = divmod(mins, 60)
    if hours > 0:
        return f"{hours:02d}:{mins:02d}:{secs:02d}"
    return f"{mins:02d}:{secs:02d}"


class GuildMusicManager:
    """Quản lý hàng chờ và phát nhạc cho từng Guild (Server) riêng biệt."""

    def __init__(self, bot, guild_id: int):
        self.bot = bot
        self.guild_id = guild_id
        self.queue = []  # Hàng chờ chứa các thông tin bài hát
        self.current = None  # Bài hát đang phát hiện tại
        self.voice_client = None
        self.text_channel = None  # Kênh chat để gửi thông báo phát nhạc
        self.loop = False  # Trạng thái lặp lại bài hát hiện tại
        self.disconnect_task = None  # Task đếm ngược tự động rời phòng

    async def add_track(self, track: dict, text_channel: discord.TextChannel) -> bool:
        """Thêm bài hát mới vào hàng chờ. Trả về True nếu phát ngay, False nếu xếp hàng."""
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
        """Phát bài tiếp theo trong hàng chờ."""
        if not self.voice_client or not self.voice_client.is_connected():
            return

        if len(self.queue) == 0 and not (self.loop and self.current):
            self.current = None
            if self.text_channel:
                embed = discord.Embed(
                    description="🎵 Đã phát hết nhạc trong danh sách chờ.",
                    color=0x5865F2,
                )
                await self.text_channel.send(embed=embed)
            return

        # Xác định bài hát tiếp theo
        if self.loop and self.current:
            track = self.current
        else:
            track = self.queue.pop(0)
            self.current = track

        try:
            # Trích xuất lại link stream trực tiếp từ Youtube do link của YouTube hết hạn sau vài giờ
            try:
                info = await self.bot.music_service.extract_info(track["webpage_url"])
                stream_url = info["url"]
            except Exception as e:
                logger.warning(f"Không thể làm mới URL stream, sử dụng URL gốc: {e}")
                stream_url = track["url"]

            source = discord.FFmpegPCMAudio(
                stream_url, **self.bot.music_service.ffmpeg_options
            )

            def after_playing(error):
                if error:
                    logger.error(
                        f"Lỗi khi phát nhạc tại server {self.guild_id}: {error}"
                    )
                # Schedule play_next() vào event loop từ audio thread
                # Dùng ensure_future thay vì lồng run_coroutine_threadsafe trong lambda
                self.bot.loop.call_soon_threadsafe(
                    asyncio.ensure_future, self.play_next()
                )

            self.voice_client.play(source, after=after_playing)

            # Gửi embed thông tin bài hát đang phát
            embed = discord.Embed(
                title="▶️ Đang phát nhạc",
                description=f"**[{track['title']}]({track['webpage_url']})**",
                color=0x57F287,  # Emerald Green
            )
            if track["thumbnail"]:
                embed.set_thumbnail(url=track["thumbnail"])
            embed.add_field(
                name="⏱️ Thời lượng",
                value=format_duration(track["duration"]),
                inline=True,
            )
            embed.add_field(name="👤 Kênh", value=track["uploader"], inline=True)
            embed.set_footer(
                text=f"Yêu cầu bởi {track.get('requester', 'Ẩn danh')}"
                + (" | 🔁 Chế độ lặp đang bật" if self.loop else "")
            )

            if self.text_channel:
                await self.text_channel.send(embed=embed)

        except Exception as e:
            logger.error(f"Lỗi khi bắt đầu phát nhạc: {e}")
            if self.text_channel:
                await self.text_channel.send(
                    f"❌ Có lỗi xảy ra khi tải bài hát **{track['title']}**: {e}"
                )
            # Thử bài hát tiếp theo
            await self.play_next()


class MusicCog(commands.Cog):
    """Cog chứa các lệnh điều khiển nhạc."""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="play",
        description="Phát nhạc từ YouTube (nhập liên kết hoặc từ khóa tìm kiếm)",
    )
    @app_commands.describe(query="Đường dẫn video YouTube hoặc từ khóa cần tìm kiếm")
    async def play(self, interaction: discord.Interaction, query: str):
        # Kiểm tra xem người dùng có ở trong kênh thoại không
        if not interaction.user.voice or not interaction.user.voice.channel:
            embed = discord.Embed(
                description="❌ Bạn cần tham gia vào một kênh thoại trước khi sử dụng lệnh này!",
                color=0xED4245,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        user_channel = interaction.user.voice.channel
        await interaction.response.defer()

        # Kết nối hoặc di chuyển bot tới kênh thoại của người dùng
        voice_client = interaction.guild.voice_client
        if not voice_client:
            try:
                voice_client = await user_channel.connect()
            except Exception as e:
                logger.error(f"Không thể kết nối đến kênh thoại: {e}")
                embed = discord.Embed(
                    description=f"❌ Không thể kết nối tới kênh thoại: {e}",
                    color=0xED4245,
                )
                await interaction.followup.send(embed=embed)
                return
        elif voice_client.channel != user_channel:
            # Di chuyển nếu bot đang rảnh rỗi
            manager = self.bot.get_manager(interaction.guild_id)
            if (
                not voice_client.is_playing()
                and not voice_client.is_paused()
                and manager.current is None
            ):
                try:
                    await voice_client.move_to(user_channel)
                except Exception as e:
                    logger.warning(f"Không thể di chuyển kênh thoại: {e}")

        # Tìm kiếm hoặc trích xuất thông tin bài hát
        try:
            info = await self.bot.music_service.extract_info(query)
        except Exception as e:
            logger.error(f"Lỗi khi trích xuất video: {e}")
            embed = discord.Embed(
                description=f"❌ Không tìm thấy kết quả hoặc có lỗi xảy ra: {e}",
                color=0xED4245,
            )
            await interaction.followup.send(embed=embed)
            return

        track = {
            "title": info.get("title", "Không có tiêu đề"),
            "url": info.get("url"),
            "webpage_url": info.get("webpage_url", query),
            "duration": info.get("duration", 0),
            "thumbnail": info.get("thumbnail"),
            "uploader": info.get("uploader", "Không xác định"),
            "requester": interaction.user.display_name,
        }

        manager = self.bot.get_manager(interaction.guild_id)
        manager.voice_client = voice_client

        started = await manager.add_track(track, interaction.channel)

        if started:
            embed = discord.Embed(
                description=f"🔍 Đang chuẩn bị phát bài hát: **[{track['title']}]({track['webpage_url']})**",
                color=0x5865F2,
            )
            await interaction.followup.send(embed=embed)
        else:
            queue_pos = len(manager.queue)
            embed = discord.Embed(
                title="📥 Đã thêm vào hàng chờ",
                description=f"**[{track['title']}]({track['webpage_url']})**",
                color=0xFEE75C,  # Yellow/Orange
            )
            if track["thumbnail"]:
                embed.set_thumbnail(url=track["thumbnail"])
            embed.add_field(
                name="⏱️ Thời lượng",
                value=format_duration(track["duration"]),
                inline=True,
            )
            embed.add_field(name="👤 Kênh", value=track["uploader"], inline=True)
            embed.add_field(
                name="🔢 Vị trí hàng chờ", value=str(queue_pos), inline=True
            )
            embed.set_footer(text=f"Yêu cầu bởi {track['requester']}")
            await interaction.followup.send(embed=embed)

    @app_commands.command(name="pause", description="Tạm dừng bài hát đang phát")
    async def pause(self, interaction: discord.Interaction):
        voice_client = interaction.guild.voice_client
        if not voice_client or not voice_client.is_playing():
            embed = discord.Embed(
                description="❌ Hiện tại không có bài hát nào đang phát!",
                color=0xED4245,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        voice_client.pause()
        embed = discord.Embed(description="⏸️ Đã tạm dừng phát nhạc.", color=0x5865F2)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="resume", description="Tiếp tục phát bài hát đang tạm dừng"
    )
    async def resume(self, interaction: discord.Interaction):
        voice_client = interaction.guild.voice_client
        if not voice_client or not voice_client.is_paused():
            embed = discord.Embed(
                description="❌ Hiện tại không có nhạc bị tạm dừng!", color=0xED4245
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        voice_client.resume()
        embed = discord.Embed(description="▶️ Đã tiếp tục phát nhạc.", color=0x5865F2)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="skip", description="Bỏ qua bài hát hiện tại")
    async def skip(self, interaction: discord.Interaction):
        voice_client = interaction.guild.voice_client
        if not voice_client or not voice_client.is_playing():
            embed = discord.Embed(
                description="❌ Không có bài hát nào đang phát để bỏ qua!",
                color=0xED4245,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # Dừng bài hát hiện tại. Hàm after_playing sẽ tự động gọi phát bài kế tiếp.
        voice_client.stop()
        embed = discord.Embed(
            description="⏭️ Đã bỏ qua bài hát hiện tại.", color=0x5865F2
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="stop", description="Dừng phát nhạc và xóa hàng chờ")
    async def stop(self, interaction: discord.Interaction):
        manager = self.bot.get_manager(interaction.guild_id)
        manager.queue.clear()
        manager.current = None
        manager.loop = False

        voice_client = interaction.guild.voice_client
        if voice_client:
            voice_client.stop()

        embed = discord.Embed(
            description="⏹️ Đã dừng nhạc và xóa sạch danh sách chờ.", color=0xED4245
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="leave", description="Rời khỏi kênh thoại hiện tại")
    async def leave(self, interaction: discord.Interaction):
        voice_client = interaction.guild.voice_client
        if not voice_client:
            embed = discord.Embed(
                description="❌ Bot hiện không ở trong bất cứ kênh thoại nào!",
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
            description="👋 Đã ngắt kết nối và dọn sạch hàng chờ.", color=0x5865F2
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="loop", description="Bật/Tắt chế độ lặp lại bài hát hiện tại"
    )
    async def loop(self, interaction: discord.Interaction):
        manager = self.bot.get_manager(interaction.guild_id)
        manager.loop = not manager.loop
        status = "BẬT" if manager.loop else "TẮT"
        embed = discord.Embed(
            description=f"🔁 Đã **{status}** chế độ lặp lại bài hát hiện tại.",
            color=0x5865F2,
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="queue", description="Hiển thị danh sách nhạc đang chờ")
    async def queue(self, interaction: discord.Interaction):
        manager = self.bot.get_manager(interaction.guild_id)

        if not manager.current and len(manager.queue) == 0:
            embed = discord.Embed(
                description="🎵 Danh sách chờ đang trống!", color=0x5865F2
            )
            await interaction.response.send_message(embed=embed)
            return

        embed = discord.Embed(title="🎵 Danh sách phát nhạc", color=0x5865F2)

        if manager.current:
            embed.add_field(
                name="▶️ Đang phát",
                value=f"**[{manager.current['title']}]({manager.current['webpage_url']})** | `{format_duration(manager.current['duration'])}` (Yêu cầu bởi: {manager.current['requester']})",
                inline=False,
            )

        if len(manager.queue) > 0:
            queue_lines = []
            for i, track in enumerate(manager.queue[:10], start=1):
                queue_lines.append(
                    f"`{i}.` **[{track['title']}]({track['webpage_url']})** | `{format_duration(track['duration'])}` (Yêu cầu bởi: {track['requester']})"
                )

            value = "\n".join(queue_lines)
            if len(manager.queue) > 10:
                value += f"\n*và {len(manager.queue) - 10} bài hát khác...*"

            embed.add_field(name="📥 Hàng chờ", value=value, inline=False)
        else:
            embed.add_field(
                name="📥 Hàng chờ",
                value="Không có bài hát nào tiếp theo trong hàng chờ.",
                inline=False,
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

        # Nếu bot không còn ở trong bất kỳ kênh thoại nào hoặc mất kết nối, hủy task và dọn dẹp state
        if (
            not voice_client
            or not voice_client.is_connected()
            or not voice_client.channel
        ):
            manager = self.bot.get_manager(member.guild.id)
            if manager.disconnect_task and not manager.disconnect_task.done():
                manager.disconnect_task.cancel()
                manager.disconnect_task = None
            # Dọn dẹp state nếu chính bot bị ngắt kết nối
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

        # Chỉ xử lý nếu sự kiện xảy ra trong kênh thoại bot đang kết nối
        in_before = before.channel == bot_channel
        in_after = after.channel == bot_channel

        if not in_before and not in_after:
            return

        # Đếm số lượng thành viên không phải bot trong kênh thoại
        non_bot_members = [m for m in bot_channel.members if not m.bot]
        manager = self.bot.get_manager(member.guild.id)

        if len(non_bot_members) == 0:
            # Nếu không còn người dùng nào, bắt đầu đếm ngược 10 giây
            if not manager.disconnect_task or manager.disconnect_task.done():
                logger.info(
                    f"All members left voice channel {bot_channel.name} in guild {member.guild.id}. Starting 10s leave timer."
                )
                manager.disconnect_task = self.bot.loop.create_task(
                    self.leave_after_delay(member.guild.id, 10)
                )
        else:
            # Nếu có người dùng quay lại/ở trong kênh thoại, hủy đếm ngược
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

        # Kiểm tra lại số lượng thành viên thực tế một lần nữa trước khi leave
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
                        description="👋 Đã rời khỏi kênh thoại vì không có người trong phòng sau 10 giây.",
                        color=0x5865F2,
                    )
                    await manager.text_channel.send(embed=embed)
                except Exception as e:
                    logger.warning(f"Không thể gửi thông báo tự động rời phòng: {e}")


class MusicBot(commands.Bot):
    """Client bot chính, xử lý kết nối và điều phối sự kiện."""

    def __init__(
        self,
        music_service: MusicService,
        event_agent_service: EventAgentService,
        task_management_agent_service: TaskManagementAgentService,
        *args,
        **kwargs,
    ):
        intents = discord.Intents.default()
        intents.voice_states = True

        super().__init__(command_prefix="!", intents=intents, *args, **kwargs)
        self.music_service = music_service
        self.event_agent_service = event_agent_service
        self.task_management_agent_service = task_management_agent_service
        self.managers = {}

    def get_manager(self, guild_id: int) -> GuildMusicManager:
        if guild_id not in self.managers:
            self.managers[guild_id] = GuildMusicManager(self, guild_id)
        return self.managers[guild_id]

    async def setup_hook(self):
        # Đăng ký Cog điều khiển nhạc
        await self.add_cog(MusicCog(self))
        # Đăng ký Cog xử lý event AI
        from app.presentation.event_cog import EventCog

        await self.add_cog(EventCog(self))
        # Đồng bộ các lệnh slash command
        await self.tree.sync()
        logger.info("Đồng bộ danh sách lệnh slash command thành công.")

    async def on_ready(self):
        logger.info(
            f"Bot đăng nhập thành công dưới tên {self.user} (ID: {self.user.id})"
        )
        logger.info("Bot đã sẵn sàng phục vụ phát nhạc!")
