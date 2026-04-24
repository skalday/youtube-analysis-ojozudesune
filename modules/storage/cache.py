import os
import time
from datetime import datetime, timezone

from modules.storage.file_store import FileStore


class CacheManager:
    def __init__(self, store: FileStore, ttl_hours: int = 24):
        self.store = store
        self.ttl_seconds = ttl_hours * 3600

    def is_fresh(self, path: str) -> bool:
        """Return True if file exists and was modified within TTL."""
        if not os.path.exists(path):
            return False
        age = time.time() - os.path.getmtime(path)
        return age < self.ttl_seconds

    def get_or_fetch(self, path: str, fetch_fn, force_refresh: bool = False):
        """Load from cache if fresh, otherwise call fetch_fn(), save, and return."""
        if not force_refresh and self.is_fresh(path):
            return self.store.load_json(path)
        data = fetch_fn()
        if data is not None:
            self.store.save_json(path, data)
        return data

    def get_cached_video_ids(self, channel_id: str) -> set:
        """Return set of video IDs already stored locally for a channel."""
        cached = self.store.load_json(self.store.video_list_path(channel_id))
        if not cached:
            return set()
        return {v["video_id"] for v in cached}

    def get_new_video_ids(self, channel_id: str, current_ids: list) -> list:
        """Return video IDs in current_ids that are NOT yet cached locally."""
        cached = self.get_cached_video_ids(channel_id)
        return [vid for vid in current_ids if vid not in cached]

    def get_cached_transcript_ids(self, channel_id: str, video_ids: list) -> set:
        """Return set of video IDs that already have a cached transcript."""
        return {
            vid for vid in video_ids
            if self.store.exists(self.store.transcript_path(channel_id, vid))
        }

    def get_cached_comment_ids(self, channel_id: str, video_ids: list) -> set:
        """Return set of video IDs that already have cached comments."""
        return {
            vid for vid in video_ids
            if self.store.exists(self.store.comments_path(channel_id, vid))
        }
