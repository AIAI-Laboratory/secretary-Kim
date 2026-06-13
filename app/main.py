import sys
from app.core.config import settings
from app.core.container import Container
from app.core.logger import get_logger

logger = get_logger(__name__)

def main():
    logger.info("Bắt đầu khởi động bot Discord Secretary Kim...")

    # Kiểm tra token Discord Bot
    if not settings.DISCORD_BOT_TOKEN:
        logger.critical(
            "\n[LỖI NGHIÊM TRỌNG] DISCORD_BOT_TOKEN chưa được thiết lập trong file .env!\n"
            "Vui lòng thêm dòng 'DISCORD_BOT_TOKEN=mã_token_bot_của_bạn' vào file .env ở thư mục gốc của dự án."
        )
        sys.exit(1)

    # Khởi tạo DI Container
    container = Container()

    # Lấy đối tượng bot duy nhất (Singleton) từ Container
    bot = container.discord_bot()

    logger.info("Đang thiết lập kết nối tới Discord...")
    try:
        bot.run(settings.DISCORD_BOT_TOKEN)
    except Exception as e:
        logger.critical(f"Lỗi khi chạy Discord bot: {e}")
        sys.exit(1)
