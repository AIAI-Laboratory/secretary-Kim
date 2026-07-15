import io
import discord
from typing import Any, Dict, List
from google.genai import types
from app.agent.skills.base import BaseSkill
from app.agent.models import SkillContext, SkillResult
from app.services.pixellab import PixelLabService, PaymentRequiredError, PixelLabError
from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)


class PixelLabSkill(BaseSkill):
    """
    Skill for generating pixel art using the PixelLab AI API.
    """

    def __init__(self, pixellab_service: PixelLabService):
        self.pixellab_service = pixellab_service

    @property
    def name(self) -> str:
        return "pixellab"

    @property
    def description(self) -> str:
        return "Tạo ảnh pixel art (nhân vật, quái vật, v.v.) từ văn bản mô tả bằng PixelLab API."

    def get_function_declarations(self) -> List[types.FunctionDeclaration]:
        return [
            types.FunctionDeclaration(
                name="generate_pixel_art",
                description="Tạo ảnh nhân vật pixel art hoặc các vật thể pixel khác từ mô tả chi tiết của người dùng.",
                parameters={
                    "type": "OBJECT",
                    "properties": {
                        "prompt": {
                            "type": "STRING",
                            "description": "Mô tả chi tiết bằng tiếng Anh về nhân vật hoặc vật thể cần sinh ảnh (ví dụ: 'a cool cyber warrior in neon armor, front view, standing stance').",
                        },
                        "model": {
                            "type": "STRING",
                            "description": "Mô hình sinh ảnh. Chọn 'pixflux' (mặc định, tối ưu cho nhân vật), 'pixen' (size lớn tới 512x512), hoặc 'bitforge' (phù hợp copy style).",
                            "enum": ["pixflux", "pixen", "bitforge"],
                        },
                        "size": {
                            "type": "STRING",
                            "description": "Kích thước pixel art mong muốn, định dạng 'widthxheight'  Mặc định là '128x128'.",
                        },
                        "transparent": {
                            "type": "BOOLEAN",
                            "description": "Tạo ảnh với nền trong suốt (không có phông nền phía sau). Mặc định là True.",
                        },
                    },
                    "required": ["prompt"],
                },
            )
        ]

    async def execute(
        self, function_name: str, args: Dict[str, Any], context: SkillContext
    ) -> SkillResult:
        if function_name != "generate_pixel_art":
            return SkillResult(
                success=False,
                message=f"Action '{function_name}' không được hỗ trợ bởi PixelLabSkill.",
            )

        client = (
            context.discord_interaction.client if context.discord_interaction else None
        )
        if not client:
            return SkillResult(
                success=False, message="Không tìm thấy Discord client trong context."
            )

        prompt = args.get("prompt")
        model = args.get("model") or "pixflux"
        size_str = args.get("size") or "64x64"
        transparent = (
            args.get("transparent") if args.get("transparent") is not None else True
        )

        # Parse size
        width, height = 128, 128
        try:
            parts = size_str.lower().split("x")
            if len(parts) == 2:
                width = int(parts[0])
                height = int(parts[1])
        except ValueError:
            pass

        # Apply constraints based on model
        if model == "pixflux":
            width = max(32, min(width, 400))
            height = max(32, min(height, 400))
        elif model == "pixen":
            width = max(32, min(width, 512))
            height = max(32, min(height, 512))
            # Must be divisible by 4
            width = (width // 4) * 4
            height = (height // 4) * 4
        elif model == "bitforge":
            width = max(32, min(width, 200))
            height = max(32, min(height, 200))

        try:
            img_bytes = await self.pixellab_service.generate_pixel_art(
                prompt=prompt,
                model=model,
                width=width,
                height=height,
                transparent=transparent,
            )

            # Upload to Discord image hosting channel to get a persistent URL
            image_channel = None
            if settings.GACHA_IMAGE_CHANNEL_ID:
                try:
                    image_channel = client.get_channel(settings.GACHA_IMAGE_CHANNEL_ID)
                    if not image_channel:
                        image_channel = await client.fetch_channel(
                            settings.GACHA_IMAGE_CHANNEL_ID
                        )
                except Exception as e:
                    logger.warning(f"Could not retrieve Discord image channel: {e}")

            if not image_channel:
                return SkillResult(
                    success=False,
                    message="Lỗi hệ thống: GACHA_IMAGE_CHANNEL_ID không được cấu hình hoặc không tìm thấy channel để upload ảnh.",
                )

            # Upload image
            file = discord.File(io.BytesIO(img_bytes), filename="pixel_art.png")
            msg = await image_channel.send(
                content=f"Pixel Art rolled by AI for user {context.user_name} ({context.user_id})",
                file=file,
            )

            if not msg.attachments:
                return SkillResult(
                    success=False, message="Lỗi upload ảnh lên Discord hosting channel."
                )

            image_url = msg.attachments[0].url

            embed = discord.Embed(
                title="🎨 Secretary Kim - Pixel Art Generated!",
                description=(
                    f"**Prompt**: {prompt}\n"
                    f"**Model**: `{model}`\n"
                    f"**Kích thước**: `{width}x{height}`\n"
                    f"**Nền trong suốt**: `{transparent}`"
                ),
                color=0x9B59B6,
            )
            embed.set_image(url=image_url)
            embed.set_footer(
                text=f"Tạo bởi PixelLab API | Yêu cầu bởi {context.user_name}"
            )

            return SkillResult(
                success=True, message="Đã tạo xong ảnh pixel của bạn!", embed=embed
            )

        except PaymentRequiredError:
            return SkillResult(
                success=False, message="Hết giờ làm rồi, đợi ngày mai nhé 😴"
            )
        except PixelLabError as e:
            logger.error(f"PixelLab error: {e}")
            return SkillResult(
                success=False, message=f"Lỗi khi kết nối tới PixelLab API: {str(e)}"
            )
        except Exception as e:
            logger.error(f"Unexpected error in PixelLabSkill: {e}", exc_info=True)
            return SkillResult(
                success=False, message=f"Lỗi không xác định khi sinh ảnh: {str(e)}"
            )
