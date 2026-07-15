from google import genai
from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)


class TaskManagementAgentService:
    def __init__(self):
        if not settings.GEMINI_API_KEY:
            logger.warning(
                "GEMINI_API_KEY chưa được cấu hình. Task Management Agent có thể gặp lỗi khi chạy."
            )
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY or None)

    # Future work: Add task management parsing / logic here
