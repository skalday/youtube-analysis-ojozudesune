import re
import time
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type


def _parse_duration_seconds(iso_duration: str) -> int:
    """Parse ISO 8601 duration string to total seconds. e.g. PT1M30S -> 90"""
    match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso_duration or "")
    if not match:
        return 0
    h = int(match.group(1) or 0)
    m = int(match.group(2) or 0)
    s = int(match.group(3) or 0)
    return h * 3600 + m * 60 + s


def _is_retryable(exc):
    if isinstance(exc, HttpError):
        return exc.resp.status in (429, 500, 503)
    return False


class YouTubeAPIClient:
    def __init__(self, api_key: str):
        self.youtube = build("youtube", "v3", developerKey=api_key)

    def get_channel_id(self, channel_input: str) -> str:
        """Resolve channel @handle or ID. Returns channel ID string."""
        channel_id, _ = self.get_channel_id_by_handle(channel_input)
        return channel_id

    def get_channel_id_by_handle(self, channel_input: str) -> tuple:
        """
        Resolve channel @handle, custom URL, or direct channel ID.
        Returns (channel_id, channel_title) tuple.
        """
        # Already a channel ID (starts with UC)
        if channel_input.startswith("UC"):
            resp = self.youtube.channels().list(
                part="snippet",
                id=channel_input,
            ).execute()
            items = resp.get("items", [])
            if items:
                return items[0]["id"], items[0]["snippet"]["title"]
            raise ValueError(f"Channel not found: {channel_input}")

        handle = channel_input.lstrip("@")

        # Try forHandle lookup (new API)
        try:
            resp = self.youtube.channels().list(
                part="snippet",
                forHandle=handle,
            ).execute()
            items = resp.get("items", [])
            if items:
                return items[0]["id"], items[0]["snippet"]["title"]
        except HttpError:
            pass

        # Fallback: search by channel name
        resp = self.youtube.search().list(
            part="snippet",
            q=handle,
            type="channel",
            maxResults=1,
        ).execute()
        items = resp.get("items", [])
        if not items:
            raise ValueError(f"Cannot find channel: {channel_input}")
        return items[0]["snippet"]["channelId"], items[0]["snippet"]["channelTitle"]

    @retry(
        retry=retry_if_exception_type(HttpError),
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=2, min=2, max=30),
    )
    def _get_uploads_playlist_id(self, channel_id: str) -> str:
        resp = self.youtube.channels().list(
            part="contentDetails",
            id=channel_id,
        ).execute()
        items = resp.get("items", [])
        if not items:
            raise ValueError(f"Channel not found: {channel_id}")
        return items[0]["contentDetails"]["relatedPlaylists"]["uploads"]

    @retry(
        retry=retry_if_exception_type(HttpError),
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=2, min=2, max=30),
    )
    def _list_playlist_page(self, playlist_id: str, page_token: str | None) -> dict:
        return self.youtube.playlistItems().list(
            part="contentDetails",
            playlistId=playlist_id,
            maxResults=50,
            pageToken=page_token,
        ).execute()

    @retry(
        retry=retry_if_exception_type(HttpError),
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=2, min=2, max=30),
    )
    def _get_video_details_batch(self, video_ids: list) -> dict:
        return self.youtube.videos().list(
            part="snippet,statistics,contentDetails",
            id=",".join(video_ids),
        ).execute()

    def list_channel_videos(self, channel_id: str, max_results: int = 20) -> list:
        """
        Return list of video metadata dicts, newest first.
        Uses uploads playlist (1 unit/page) instead of search.list (100 units/page).
        Each dict: {video_id, title, published_at, description,
                    view_count, like_count, comment_count, duration, thumbnail_url}
        """
        playlist_id = self._get_uploads_playlist_id(channel_id)

        video_ids = []
        page_token = None

        while len(video_ids) < max_results:
            resp = self._list_playlist_page(playlist_id, page_token)

            for item in resp.get("items", []):
                video_ids.append(item["contentDetails"]["videoId"])
                if len(video_ids) >= max_results:
                    break

            page_token = resp.get("nextPageToken")
            if not page_token:
                break

        if not video_ids:
            return []

        # Batch fetch details (max 50 per request)
        videos = []
        for i in range(0, len(video_ids), 50):
            batch = video_ids[i:i + 50]
            resp = self._get_video_details_batch(batch)
            for item in resp.get("items", []):
                snippet = item.get("snippet", {})
                stats = item.get("statistics", {})
                thumbnails = snippet.get("thumbnails", {})
                thumb = (
                    thumbnails.get("maxres")
                    or thumbnails.get("high")
                    or thumbnails.get("medium")
                    or thumbnails.get("default")
                    or {}
                )
                duration_iso = item.get("contentDetails", {}).get("duration", "")
                duration_sec = _parse_duration_seconds(duration_iso)
                videos.append({
                    "video_id": item["id"],
                    "title": snippet.get("title", ""),
                    "published_at": snippet.get("publishedAt", ""),
                    "description": snippet.get("description", ""),
                    "view_count": int(stats.get("viewCount", 0)),
                    "like_count": int(stats.get("likeCount", 0)),
                    "comment_count": int(stats.get("commentCount", 0)),
                    "duration": duration_iso,
                    "duration_seconds": duration_sec,
                    "is_short": duration_sec < 300,
                    "thumbnail_url": thumb.get("url", ""),
                    "channel_id": snippet.get("channelId", ""),
                    "channel_title": snippet.get("channelTitle", ""),
                })

        # Sort by published_at descending
        videos.sort(key=lambda v: v["published_at"], reverse=True)
        return videos
