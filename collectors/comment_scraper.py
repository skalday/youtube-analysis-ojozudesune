from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from tqdm import tqdm


def _is_retryable(exc):
    if isinstance(exc, HttpError):
        return exc.resp.status in (429, 500, 503)
    return False


class CommentScraper:
    def __init__(self, api_key: str, max_per_video: int = 100):
        self.youtube = build("youtube", "v3", developerKey=api_key)
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
        """
        Fetch top-level comments for a video.
        Returns list of comment dicts.
        """
        comments = []
        page_token = None

        try:
            while len(comments) < self.max_per_video:
                resp = self._fetch_page(video_id, page_token)

                for item in resp.get("items", []):
                    top = item["snippet"]["topLevelComment"]["snippet"]
                    comments.append({
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
            # Comments disabled or other API error — return what we have
            if e.resp.status == 403:
                return comments
            raise

        return comments[: self.max_per_video]

    def fetch_batch(self, video_ids: list, skip_existing_ids: set | None = None) -> dict:
        """
        Fetch comments for multiple videos.
        Returns {video_id: [comment_dict, ...]}
        """
        results = {}
        skip = skip_existing_ids or set()
        to_fetch = [vid for vid in video_ids if vid not in skip]

        for video_id in tqdm(to_fetch, desc="抓取留言", unit="支"):
            results[video_id] = self.fetch_comments(video_id)

        return results
