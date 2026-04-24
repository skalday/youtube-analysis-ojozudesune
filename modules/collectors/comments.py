from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from tqdm import tqdm


class CommentScraper:
    def __init__(self, api_client=None, store=None, max_per_video: int = 100, api_key: str | None = None):
        if api_client is not None:
            self.youtube = api_client.youtube
        elif api_key is not None:
            self.youtube = build("youtube", "v3", developerKey=api_key)
        else:
            raise ValueError("Either api_client or api_key must be provided")
        self.store = store
        self.max_per_video = max_per_video

    @retry(
        retry=retry_if_exception_type(HttpError),
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=2, min=2, max=30),
    )
    def _fetch_page(self, video_id: str, page_token: str | None) -> dict:
        return self.youtube.commentThreads().list(
            part="snippet",
            videoId=video_id,
            order="relevance",
            maxResults=min(self.max_per_video, 100),
            pageToken=page_token,
            textFormat="plainText",
        ).execute()

    def fetch_comments(self, video_id: str) -> list:
        """Fetch top-level comments for a video. Returns list of comment dicts."""
        comments = []
        page_token = None

        try:
            while len(comments) < self.max_per_video:
                resp = self._fetch_page(video_id, page_token)

                for item in resp.get("items", []):
                    top = item["snippet"]["topLevelComment"]["snippet"]
                    comments.append({
                        "video_id": video_id,
                        "comment_id": item["id"],
                        "author": top.get("authorDisplayName", ""),
                        "text": top.get("textDisplay", ""),
                        "like_count": top.get("likeCount", 0),
                        "reply_count": item["snippet"].get("totalReplyCount", 0),
                        "published_at": top.get("publishedAt", ""),
                        "updated_at": top.get("updatedAt", ""),
                    })

                page_token = resp.get("nextPageToken")
                if not page_token or len(comments) >= self.max_per_video:
                    break

        except HttpError as e:
            if e.resp.status == 403:
                return comments
            raise

        comments = comments[: self.max_per_video]
        comments.sort(key=lambda c: (c["like_count"], c["reply_count"]), reverse=True)
        return comments

    def fetch_batch(
        self,
        video_ids: list,
        fetch_ids: list | None = None,
        channel_id: str | None = None,
        force: bool = False,
    ) -> dict:
        """
        Fetch comments for multiple videos, using cache for non-fetch_ids.
        Returns {video_id: [comment_dict, ...]} for all video_ids.
        """
        fetch_set = set(fetch_ids if fetch_ids is not None else video_ids)
        results = {}

        to_fetch = []
        for video_id in video_ids:
            if not force and video_id not in fetch_set:
                if self.store and channel_id:
                    path = self.store.comments_path(channel_id, video_id)
                    cached = self.store.load_json(path)
                    if cached is not None:
                        results[video_id] = cached
                        continue
            to_fetch.append(video_id)

        for video_id in tqdm(to_fetch, desc="Fetching comments", unit="vid"):
            comments = self.fetch_comments(video_id)
            results[video_id] = comments
            if self.store and channel_id:
                path = self.store.comments_path(channel_id, video_id)
                self.store.save_json(path, comments)

        return results
