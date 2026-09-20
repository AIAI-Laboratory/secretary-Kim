"""Business service for YouTube audio stream retrieval and URL processing."""

import asyncio
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import yt_dlp


def clean_youtube_url(url: str) -> str:
    """Remove redundant playlist or tracking parameters in YouTube links.

    Args:
        url (str): Raw YouTube URL.

    Returns:
        str: Cleaned URL targeting only the single video.
    """
    try:
        parsed = urlparse(url)
        # Link style youtube.com/watch?v=...
        if "youtube.com" in parsed.netloc and "watch" in parsed.path:
            query_params = parse_qs(parsed.query)
            if "v" in query_params:
                new_query = urlencode({"v": query_params["v"][0]})
                return urlunparse(parsed._replace(query=new_query))
        # Short link style youtu.be/...
        elif "youtu.be" in parsed.netloc:
            return urlunparse(parsed._replace(query=""))
    except (ValueError, AttributeError):
        pass
    return url


class MusicService:
    """Service handling audio stream extraction and FFmpeg playback configurations."""

    def __init__(self) -> None:
        """Initialize yt-dlp and FFmpeg streaming options."""
        # Optimize yt-dlp configuration for audio stream extraction
        self.ydl_opts = {
            "format": "bestaudio/best",
            "quiet": True,
            "no_warnings": True,
            "default_search": "ytsearch",
            "source_address": "0.0.0.0",  # Bind to IPv4 to avoid IPv6 network issues
            "nocheckcertificate": True,
            "noplaylist": True,  # Only fetch info of single video, ignore playlist
        }

        # FFmpeg configuration for smooth streaming, support auto reconnect on network interruptions
        self.ffmpeg_options = {
            "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
            "options": "-vn",
        }

    async def extract_info(self, query: str) -> dict[str, Any]:
        """Extract stream info from a YouTube link or search query without downloading.

        Runs in a worker thread to avoid blocking the asyncio event loop.

        Args:
            query (str): Song title search string or YouTube URL.

        Returns:
            dict[str, Any]: Metadata dictionary of the extracted audio stream.

        Raises:
            ValueError: If search yields no valid entries.
        """
        cleaned_query = clean_youtube_url(query)

        def _extract():
            with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                info = ydl.extract_info(cleaned_query, download=False)
                if "entries" in info:
                    # If it is a search result, take the first entry
                    if not info["entries"]:
                        raise ValueError("No matching search result found.")
                    info = info["entries"][0]
                return info

        return await asyncio.to_thread(_extract)
