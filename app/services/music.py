import yt_dlp
import asyncio

class MusicService:
    def __init__(self):
        # Cấu hình yt-dlp tối ưu cho việc trích xuất audio stream
        self.ydl_opts = {
            'format': 'bestaudio/best',
            'quiet': True,
            'no_warnings': True,
            'default_search': 'ytsearch',
            'source_address': '0.0.0.0',  # Ràng buộc với IPv4 tránh các lỗi mạng IPv6
            'nocheckcertificate': True,
        }
        
        # Cấu hình FFmpeg để stream mượt mà, hỗ trợ tự động kết nối lại khi mạng gián đoạn
        self.ffmpeg_options = {
            'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
            'options': '-vn',
        }

    async def extract_info(self, query: str) -> dict:
        """
        Trích xuất thông tin stream từ link YouTube hoặc từ khóa tìm kiếm (không tải về).
        Chạy trong một luồng riêng biệt (thread) để tránh làm nghẽn event loop chính.
        """
        def _extract():
            with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                info = ydl.extract_info(query, download=False)
                if 'entries' in info:
                    # Nếu là kết quả tìm kiếm, lấy phần tử đầu tiên
                    if not info['entries']:
                        raise Exception("Không tìm thấy kết quả tìm kiếm phù hợp.")
                    info = info['entries'][0]
                return info

        return await asyncio.to_thread(_extract)
