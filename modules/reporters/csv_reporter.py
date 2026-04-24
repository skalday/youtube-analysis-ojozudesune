from __future__ import annotations

from pathlib import Path

from modules.storage.file_store import FileStore


class CSVReporter:
    def __init__(self, store: FileStore):
        self.store = store

    def write_comments(self, out_dir: str | Path, all_comments: dict, videos: list) -> Path:
        out_dir = Path(out_dir)
        path = out_dir / "comments.csv"

        video_meta = {v["video_id"]: v for v in videos}
        records = []

        for video_id, comments in all_comments.items():
            meta = video_meta.get(video_id, {})
            title = meta.get("title", "")
            url = f"https://youtu.be/{video_id}"
            for c in (comments or []):
                records.append({
                    "video_id": video_id,
                    "video_title": title,
                    "video_url": url,
                    "text": c.get("text", ""),
                    "author": c.get("author", ""),
                    "like_count": c.get("like_count", 0),
                    "reply_count": c.get("reply_count", 0),
                    "published_at": c.get("published_at", ""),
                })

        self.store.save_csv(str(path), records)
        print(f"  [csv] written {path} ({len(records)} comments)")
        return path

    def write_transcripts(self, out_dir: str | Path, transcripts: dict, videos: list) -> Path:
        out_dir = Path(out_dir)
        path = out_dir / "transcripts.csv"

        video_meta = {v["video_id"]: v for v in videos}
        records = []

        for video_id, transcript in transcripts.items():
            meta = video_meta.get(video_id, {})
            title = meta.get("title", "")
            url = f"https://youtu.be/{video_id}"
            if transcript:
                records.append({
                    "video_id": video_id,
                    "video_title": title,
                    "video_url": url,
                    "language": transcript.get("language", ""),
                    "is_generated": transcript.get("is_generated", ""),
                    "full_text": transcript.get("full_text", ""),
                })
            else:
                records.append({
                    "video_id": video_id,
                    "video_title": title,
                    "video_url": url,
                    "language": "",
                    "is_generated": "",
                    "full_text": "(no transcript)",
                })

        self.store.save_csv(str(path), records)
        print(f"  [csv] written {path} ({len(records)} videos)")
        return path

