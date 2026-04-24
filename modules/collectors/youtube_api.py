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


class YouTubeAPIClient:
    def __init__(self, api_key: str):
        self.youtube = build("youtube", "v3", developerKey=api_key)

    def get_channel_id_by_handle(self, channel_input: str) -> tuple[str, str]:
        """
        Resolve channel @handle, custom URL, or direct channel ID.
        Returns (channel_id, channel_title).
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

    def _parse_video_item(self, item: dict) -> dict:
        snippet = item.get("snippet", {})
        stats = item.get("statistics", {})
        thumbnails = snippet.get("thumbnails", {})
        thumb = (
            thumbnails.get("maxres") or thumbnails.get("high")
            or thumbnails.get("medium") or thumbnails.get("default") or {}
        )
        duration_iso = item.get("contentDetails", {}).get("duration", "")
        duration_sec = _parse_duration_seconds(duration_iso)
        return {
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
        }

    def list_channel_videos(self, channel_id: str, max_results: int = 20, published_after: str | None = None) -> list:
        """
        Return list of video metadata dicts, newest first.
        If published_after (ISO timestamp) is given, return only videos newer than that date.
        """
        playlist_id = self._get_uploads_playlist_id(channel_id)

        if published_after:
            return self._list_videos_since(playlist_id, published_after)

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

        videos = []
        for i in range(0, len(video_ids), 50):
            resp = self._get_video_details_batch(video_ids[i:i + 50])
            for item in resp.get("items", []):
                videos.append(self._parse_video_item(item))

        videos.sort(key=lambda v: v["published_at"], reverse=True)
        return videos

    def _list_videos_since(self, playlist_id: str, published_after: str) -> list:
        """Page through the uploads playlist and collect videos published after the given ISO timestamp."""
        videos = []
        page_token = None

        while True:
            resp = self._list_playlist_page(playlist_id, page_token)
            batch_ids = [item["contentDetails"]["videoId"] for item in resp.get("items", [])]
            if not batch_ids:
                break

            details = self._get_video_details_batch(batch_ids)
            stop = False
            for item in details.get("items", []):
                video = self._parse_video_item(item)
                if video["published_at"] > published_after:
                    videos.append(video)
                else:
                    stop = True

            page_token = resp.get("nextPageToken")
            if not page_token or stop:
                break

        videos.sort(key=lambda v: v["published_at"], reverse=True)
        return videos
