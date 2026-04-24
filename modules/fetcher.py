"""
High-level fetch orchestration.

Usage:
    from modules.fetcher import YouTubeFetcher
    from config.settings import load_settings

    settings = load_settings()
    fetcher = YouTubeFetcher(settings)
    channel_id, channel_title, videos, transcripts, comments = fetcher.fetch("@SomeChannel")
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from modules.collectors.youtube_api import YouTubeAPIClient
from modules.collectors.transcript import TranscriptFetcher
from modules.collectors.comments import CommentScraper
from modules.storage.file_store import FileStore
from modules.storage.cache import CacheManager


class YouTubeFetcher:
    def __init__(self, settings):
        self.settings = settings
        self.store = FileStore(base_dir=settings.data_dir)
        self.cache = CacheManager(self.store)
        self.yt = YouTubeAPIClient(api_key=settings.youtube_api_key)
        self.tf = TranscriptFetcher(
            preferred_languages=settings.transcript_languages,
            store=self.store,
        )
        self.cs = CommentScraper(
            api_client=self.yt,
            store=self.store,
            max_per_video=settings.max_comments_per_video,
        )

    def fetch(self, channel: str) -> tuple[str, str, list, dict, dict]:
        """
        Resolve channel, fetch videos/transcripts/comments, and cache to disk.
        Returns (channel_id, channel_title, videos, transcripts, comments).
        """
        print(f"\n>>> Resolving channel: {channel}")
        try:
            channel_id, channel_title = self.yt.get_channel_id_by_handle(channel)
            print(f"    {channel_title} ({channel_id})")
        except Exception as exc:
            print(f"Failed to resolve channel: {exc}", file=sys.stderr)
            sys.exit(1)

        print("\n>>> Fetching video list...")
        try:
            videos = self.yt.list_channel_videos(
                channel_id=channel_id, max_results=self.settings.max_videos
            )
            self.store.save_json(self.store.video_list_path(channel_id), videos)
        except Exception as exc:
            print(f"Failed to fetch video list: {exc}", file=sys.stderr)
            sys.exit(1)

        shorts_count = sum(1 for v in videos if v.get("is_short"))
        print(f"    {len(videos)} videos  (Regular: {len(videos) - shorts_count} / Shorts: {shorts_count})")

        all_video_ids = (
            [v["video_id"] for v in videos if not v.get("is_short")]
            + [v["video_id"] for v in videos if v.get("is_short")]
        )
        new_video_ids = self.cache.get_new_video_ids(channel_id, all_video_ids)
        print(f"    New: {len(new_video_ids)} / Cached: {len(all_video_ids) - len(new_video_ids)}")

        transcripts: dict = {}
        print("\n>>> Fetching transcripts (new videos only)...")
        try:
            transcripts = self.tf.fetch_batch(
                video_ids=all_video_ids,
                new_only_ids=new_video_ids,
                channel_id=channel_id,
            )
            fetched = sum(1 for t in transcripts.values() if t)
            print(f"    {fetched} / {len(all_video_ids)} transcripts fetched")
            transcript_set = {vid for vid, t in transcripts.items() if t}
            for v in videos:
                v["has_transcript"] = v["video_id"] in transcript_set
        except Exception as exc:
            print(f"[WARNING] Transcript fetch failed: {exc}", file=sys.stderr)

        all_comments: dict = {}
        print("\n>>> Fetching comments (regular videos only)...")
        try:
            regular_ids = [v["video_id"] for v in videos if not v.get("is_short")]
            new_regular = [vid for vid in new_video_ids if vid in set(regular_ids)]
            all_comments = self.cs.fetch_batch(
                video_ids=regular_ids,
                fetch_ids=new_regular,
                channel_id=channel_id,
            )
            total = sum(len(c) for c in all_comments.values())
            print(f"    {total} comments across {len(all_comments)} videos")
        except Exception as exc:
            print(f"[WARNING] Comment fetch failed: {exc}", file=sys.stderr)

        return channel_id, channel_title, videos, transcripts, all_comments

    def load_cached(self, channel_id: str) -> tuple[list, dict, dict]:
        """Load videos, transcripts, and comments from local disk cache."""
        data_dir = Path(self.settings.data_dir)

        videos: list = []
        vpath = data_dir / "raw" / "videos" / channel_id / "video_list.json"
        if vpath.exists():
            with open(vpath, encoding="utf-8") as f:
                videos = json.load(f)

        transcripts: dict = {}
        td = data_dir / "raw" / "transcripts" / channel_id
        if td.exists():
            for p in td.glob("*.json"):
                with open(p, encoding="utf-8") as f:
                    transcripts[p.stem] = json.load(f)

        all_comments: dict = {}
        cd = data_dir / "raw" / "comments" / channel_id
        if cd.exists():
            for p in cd.glob("*.json"):
                with open(p, encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        all_comments[p.stem] = data

        return videos, transcripts, all_comments
