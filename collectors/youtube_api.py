import time
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type


def _is_retryable(exc):
    if isinstance(exc, HttpError):
        return exc.resp.status in (429, 500, 503)
    return False


class YouTubeAPIClient:
    def __init__(self, api_key: str):
        self.youtube = build("youtube", "v3", developerKey=api_key)

    def get_channel_id_by_handle(self, channel_input: str) -> tuple[str, str]:
        """
        Resolve channel @handle, custom URL, or direct channel ID.
        Returns (channel_id, channel_title).
        """
        channel_id = self.get_channel_id(channel_input)
        resp = self.youtube.channels().list(
            part="snippet",
            id=channel_id,
        ).execute()
        items = resp.get("items", [])
        title = items[0]["snippet"]["title"] if items else channel_id
        return channel_id, title

    def get_channel_id(self, channel_input: str) -> str:
        """
        Resolve channel @handle, custom URL, or direct channel ID.
        Returns channel ID string.
        """
        # Already a channel ID (starts with UC)
        if channel_input.startswith("UC"):
            return channel_input

        handle = channel_input.lstrip("@")

        # Try forHandle lookup (new API)
        try:
            resp = self.youtube.channels().list(
                part="id",
                forHandle=handle,
            ).execute()
            items = resp.get("items", [])
            if items:
                return items[0]["id"]
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
        return items[0]["snippet"]["channelId"]

    @retry(
        retry=retry_if_exception_type(HttpError),
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=2, min=2, max=30),
    )
    def _list_videos_page(self, channel_id: str, page_token: str | None, max_results: int) -> dict:
        return self.youtube.search().list(
            part="id",
            channelId=channel_id,
            type="video",
            order="date",
            maxResults=min(max_results, 50),
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
        Each dict: {video_id, title, published_at, description,
                    view_count, like_count, comment_count, duration, thumbnail_url}
        """
        video_ids = []
        page_token = None

        while len(video_ids) < max_results:
            fetch_count = min(max_results - len(video_ids), 50)
            resp = self._list_videos_page(channel_id, page_token, fetch_count)

            for item in resp.get("items", []):
                video_ids.append(item["id"]["videoId"])

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
                videos.append({
                    "video_id": item["id"],
                    "title": snippet.get("title", ""),
                    "published_at": snippet.get("publishedAt", ""),
                    "description": snippet.get("description", ""),
                    "view_count": int(stats.get("viewCount", 0)),
                    "like_count": int(stats.get("likeCount", 0)),
                    "comment_count": int(stats.get("commentCount", 0)),
                    "duration": item.get("contentDetails", {}).get("duration", ""),
                    "thumbnail_url": thumb.get("url", ""),
                    "channel_id": snippet.get("channelId", ""),
                    "channel_title": snippet.get("channelTitle", ""),
                })

        # Sort by published_at descending
        videos.sort(key=lambda v: v["published_at"], reverse=True)
        return videos
