from google import genai
from google.genai import types
from app.core.config import settings
from app.domain.models.event import ProposedAction
from app.core.logger import get_logger

logger = get_logger(__name__)


class EventAgentService:
    def __init__(self):
        if not settings.GEMINI_API_KEY:
            logger.warning(
                "GEMINI_API_KEY chưa được cấu hình. AI Agent có thể gặp lỗi khi chạy."
            )
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY or None)

    async def parse_prompt(
        self,
        prompt: str,
        user_list: dict[str, str],
        channel_list: dict[str, str],
        current_time_info: str,
    ) -> ProposedAction:
        """
        Phân tích câu lệnh tự nhiên của người dùng bằng Gemini và trích xuất thành ProposedAction.

        Args:
            prompt: Câu lệnh tự nhiên của người dùng (vd: "Tạo một task thiết kế giao diện mobile hạn chót là thứ sáu này gán cho Duy")
            user_list: Danh sách user trong server dạng {id: display_name}
            channel_list: Danh sách phòng thoại (voice channels) trong server dạng {id: channel_name}
            current_time_info: Thông tin ngày giờ hiện tại để phân tích mốc thời gian tương đối

        Returns:
            ProposedAction: Đối tượng chứa thông tin event/task đã trích xuất, hoặc đối tượng có is_valid_event=False nếu có lỗi.
        """
        system_instruction = (
            "Bạn là Thư Ký Kim, một trợ lý AI thông minh trên Discord. "
            "Nhiệm vụ của bạn là phân tích câu lệnh tự nhiên của người dùng và trích xuất thông tin để tạo event/task trên Discord. "
            f"Thông tin thời gian hiện tại của hệ thống: {current_time_info}. "
            f"Danh sách thành viên trong server (key là Discord ID, value là Tên hiển thị): {user_list}. "
            f"Danh sách phòng thoại (voice channels) trong server (key là Channel ID, value là Tên phòng thoại): {channel_list}. "
            "Hãy chuyển đổi các mốc thời gian tương đối như 'thứ sáu tuần này', 'ngày mai', 'tối nay', 'tuần sau' thành ngày giờ chính xác ở định dạng ISO 8601 (múi giờ +07:00). "
            "Nếu người dùng muốn gán task cho một người, hãy tìm người đó trong danh sách thành viên được cung cấp. Nếu tìm thấy, điền cả assignee_id and assignee_name. "
            "Nếu người dùng đề cập đến địa điểm hoặc room họp (ví dụ: 'tại room meeting-room') và nó trùng/khớp với một phòng thoại (voice channel) trong danh sách, "
            "hãy điền `channel_id` và `channel_name` tương ứng, đồng thời đặt `location` là null. "
            "Nếu địa điểm được yêu cầu không trùng phòng thoại nào, hãy đặt `channel_id` và `channel_name` là null, và điền địa điểm vào `location`. "
            "Nếu yêu cầu không rõ ràng, thiếu thông tin quan trọng hoặc không liên quan đến việc tạo event/task, hãy đặt is_valid_event = false."
        )

        try:
            logger.info(f"Đang gửi yêu cầu phân tích tới Gemini: {prompt}")
            response = await self.client.aio.models.generate_content(
                model=settings.GEMINI_PRIMARY_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json",
                    response_schema=ProposedAction,
                    temperature=0.1,
                ),
            )

            json_text = response.text
            logger.debug(f"Kết quả trả về từ Gemini: {json_text}")

            action = ProposedAction.model_validate_json(json_text)
            return action
        except Exception as e:
            logger.error(
                f"Lỗi khi xử lý ngôn ngữ tự nhiên bằng Gemini: {e}", exc_info=True
            )
            return ProposedAction(is_valid_event=False)
