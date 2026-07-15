import yt_dlp
import asyncio
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse


def clean_youtube_url(url: str) -> str:
    """Loại bỏ các tham số playlist hoặc tracking thừa trong link YouTube."""
    try:
        parsed = urlparse(url)
        # Link dạng youtube.com/watch?v=...
        if "youtube.com" in parsed.netloc and "watch" in parsed.path:
            query_params = parse_qs(parsed.query)
            if "v" in query_params:
                new_query = urlencode({"v": query_params["v"][0]})
                return urlunparse(parsed._replace(query=new_query))
        # Link rút gọn dạng youtu.be/...
        elif "youtu.be" in parsed.netloc:
            return urlunparse(parsed._replace(query=""))
    except Exception:
        pass
    return url


class MusicService:
    def __init__(self):
        # Cấu hình yt-dlp tối ưu cho việc trích xuất audio stream
        self.ydl_opts = {
            "format": "bestaudio/best",
            "quiet": True,
            "no_warnings": True,
            "default_search": "ytsearch",
            "source_address": "0.0.0.0",  # Ràng buộc với IPv4 tránh các lỗi mạng IPv6
            "nocheckcertificate": True,
            "noplaylist": True,  # Chỉ lấy thông tin của video đơn lẻ, bỏ qua playlist
        }

        # Cấu hình FFmpeg để stream mượt mà, hỗ trợ tự động kết nối lại khi mạng gián đoạn
        self.ffmpeg_options = {
            "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
            "options": "-vn",
        }

    async def extract_info(self, query: str) -> dict:
        """
        Trích xuất thông tin stream từ link YouTube hoặc từ khóa tìm kiếm (không tải về).
        Chạy trong một luồng riêng biệt (thread) để tránh làm nghẽn event loop chính.
        """
        cleaned_query = clean_youtube_url(query)

        def _extract():
            with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                info = ydl.extract_info(cleaned_query, download=False)
                if "entries" in info:
                    # Nếu là kết quả tìm kiếm, lấy phần tử đầu tiên
                    if not info["entries"]:
                        raise Exception("Không tìm thấy kết quả tìm kiếm phù hợp.")
                    info = info["entries"][0]
                return info

        return await asyncio.to_thread(_extract)
