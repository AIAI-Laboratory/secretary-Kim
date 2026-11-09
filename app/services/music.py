"""Business service for YouTube audio stream retrieval and URL processing."""

import asyncio
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import yt_dlp


def is_youtube_playlist_url(url: str) -> bool:
    """Check if the given URL is a YouTube playlist or contains a playlist parameter.

    Args:
        url (str): YouTube URL string.

    Returns:
        bool: True if the URL refers to or includes a playlist.
    """
    try:
        parsed = urlparse(url)
        netloc = parsed.netloc.lower()
        if "youtube.com" in netloc or "youtu.be" in netloc:
            query_params = parse_qs(parsed.query)
            return "list" in query_params or "playlist" in parsed.path
    except (ValueError, AttributeError):
        pass
    return False


def clean_youtube_url(url: str, force_single: bool = False) -> str:
    """Clean redundant tracking parameters from YouTube links while preserving playlist parameters.

    Args:
        url (str): Raw YouTube URL or search query.
        force_single (bool): If True, strip playlist parameters to target only the single video. Defaults to False.

    Returns:
        str: Cleaned URL targeting the media resource.
    """
    try:
        parsed = urlparse(url)
        netloc = parsed.netloc.lower()
        if "youtube.com" in netloc or "youtu.be" in netloc:
            query_params = parse_qs(parsed.query)
            keep_params = {}
            if "v" in query_params:
                keep_params["v"] = query_params["v"][0]
            if "list" in query_params and not force_single:
                keep_params["list"] = query_params["list"][0]

            # Short link style youtu.be/<video_id>
            if "youtu.be" in netloc:
                video_id = parsed.path.strip("/")
                if "list" in keep_params:
                    return f"https://www.youtube.com/watch?v={video_id}&list={keep_params['list']}"
                elif video_id:
                    return f"https://www.youtube.com/watch?v={video_id}"

            # Playlist path youtube.com/playlist
            if "playlist" in parsed.path:
                if "list" in query_params and not force_single:
                    return urlunparse(
                        parsed._replace(
                            query=urlencode({"list": query_params["list"][0]})
                        )
                    )
                return url

            # Standard watch path youtube.com/watch
            if "watch" in parsed.path and keep_params:
                return urlunparse(parsed._replace(query=urlencode(keep_params)))
    except (ValueError, AttributeError):
        pass
    return url


class MusicService:
    """Service handling audio stream extraction and FFmpeg playback configurations."""

    def __init__(self) -> None:
        """Initialize yt-dlp and FFmpeg streaming options."""
        # Optimize yt-dlp configuration for single track audio stream extraction
        self.ydl_opts = {
            "format": "bestaudio/best",
            "quiet": True,
            "no_warnings": True,
            "default_search": "ytsearch",
            "source_address": "0.0.0.0",  # Bind to IPv4 to avoid IPv6 network issues
            "nocheckcertificate": True,
            "noplaylist": True,  # Only fetch info of single video, ignore playlist
        }

        # Configuration for extracting playlist metadata without pre-resolving every audio stream
        self.ydl_playlist_opts = {
            "format": "bestaudio/best",
            "quiet": True,
            "no_warnings": True,
            "source_address": "0.0.0.0",
            "nocheckcertificate": True,
            "noplaylist": False,
            "extract_flat": "in_playlist",
        }

        # FFmpeg configuration for smooth streaming, support auto reconnect on network interruptions
        self.ffmpeg_options = {
            "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
            "options": "-vn",
        }

    async def extract_info(
        self, query: str, force_single: bool = False
    ) -> dict[str, Any]:
        """Extract stream info or playlist metadata from a YouTube link or search query.

        Runs in a worker thread to avoid blocking the asyncio event loop.

        Args:
            query (str): Song title search string or YouTube URL.
            force_single (bool): If True, extract only the single video stream even if playlist parameters exist. Defaults to False.

        Returns:
            dict[str, Any]: Metadata dictionary of the extracted audio stream or playlist.

        Raises:
            ValueError: If search yields no valid entries or extraction fails.
        """
        cleaned_query = clean_youtube_url(query, force_single=force_single)
        is_playlist = (not force_single) and is_youtube_playlist_url(cleaned_query)

        def _extract() -> dict[str, Any]:
            opts = self.ydl_playlist_opts if is_playlist else self.ydl_opts
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(cleaned_query, download=False)
                if not info:
                    raise ValueError("No matching search result or media found.")

                # Check if the extracted result is a playlist
                if (
                    info.get("_type") == "playlist"
                    and "search" not in info.get("extractor", "").lower()
                ):
                    raw_entries = info.get("entries") or []
                    valid_entries = []
                    for entry in raw_entries:
                        if not entry:
                            continue
                        if entry.get("title") in ("[Private video]", "[Deleted video]"):
                            continue
                        vid = entry.get("id")
                        webpage = entry.get("webpage_url") or entry.get("url")
                        if not webpage and vid:
                            webpage = f"https://www.youtube.com/watch?v={vid}"
                        if not webpage:
                            continue

                        thumb = entry.get("thumbnail")
                        if not thumb and entry.get("thumbnails"):
                            thumb = entry["thumbnails"][-1].get("url")
                        if not thumb and vid:
                            thumb = f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"

                        valid_entries.append(
                            {
                                "id": vid,
                                "title": entry.get("title") or "No Title",
                                "webpage_url": webpage,
                                "url": (
                                    entry.get("url")
                                    if entry.get("url", "").startswith("http")
                                    and "googlevideo.com" in entry.get("url", "")
                                    else None
                                ),
                                "duration": int(entry.get("duration") or 0),
                                "thumbnail": thumb,
                                "uploader": (
                                    entry.get("uploader")
                                    or entry.get("channel")
                                    or "Unknown"
                                ),
                            }
                        )

                    if not valid_entries:
                        raise ValueError(
                            "No playable tracks found in playlist (may be private or empty)."
                        )

                    # Limit to first 100 entries to prevent memory and queue overload
                    valid_entries = valid_entries[:100]

                    return {
                        "is_playlist": True,
                        "_type": "playlist",
                        "title": info.get("title") or "YouTube Playlist",
                        "webpage_url": cleaned_query,
                        "uploader": (
                            info.get("uploader") or info.get("channel") or "YouTube"
                        ),
                        "thumbnail": info.get("thumbnail")
                        or (valid_entries[0]["thumbnail"] if valid_entries else None),
                        "entries": valid_entries,
                        "track_count": len(valid_entries),
                    }

                # If it is a search result, take the first entry
                if "entries" in info:
                    if not info["entries"]:
                        raise ValueError("No matching search result found.")
                    info = info["entries"][0]
                return info

        return await asyncio.to_thread(_extract)
