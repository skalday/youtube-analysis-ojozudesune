"""
CSVReporter — Export raw data as CSV (UTF-8-sig, Excel compatible).
"""
from __future__ import annotations

from pathlib import Path

from storage.file_store import FileStore


class CSVReporter:
    def __init__(self, store: FileStore):
        self.store = store

    # ------------------------------------------------------------------
    # comments.csv
    # ------------------------------------------------------------------

    def write_comments(
        self,
        out_dir: str | Path,
        all_comments: dict,
        videos: list,
    ) -> Path:
        """
        Args:
            all_comments: {video_id: [comment_dict]}
            videos: [video_dict with video_id, title]
        """
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

    # ------------------------------------------------------------------
    # transcripts.csv
    # ------------------------------------------------------------------

    def write_transcripts(
        self,
        out_dir: str | Path,
        transcripts: dict,
        videos: list,
    ) -> Path:
        """
        Args:
            transcripts: {video_id: transcript_dict_or_None}
            videos: [video_dict]
        """
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

    # ------------------------------------------------------------------
    # locations_database.csv / food_database.csv / equipment_database.csv
    # ------------------------------------------------------------------

    def write_locations(
        self,
        out_dir: str | Path,
        location_agg: dict,
    ) -> Path:
        out_dir = Path(out_dir)
        path = out_dir / "locations_database.csv"
        records = location_agg.get("all_locations", [])
        self.store.save_csv(str(path), records)
        print(f"  [csv] written {path} ({len(records)} locations)")
        return path

    def write_food(
        self,
        out_dir: str | Path,
        location_agg: dict,
    ) -> Path:
        out_dir = Path(out_dir)
        path = out_dir / "food_database.csv"
        records = location_agg.get("all_food", [])
        self.store.save_csv(str(path), records)
        print(f"  [csv] written {path} ({len(records)} food items)")
        return path

    def write_equipment(
        self,
        out_dir: str | Path,
        location_agg: dict,
    ) -> Path:
        out_dir = Path(out_dir)
        path = out_dir / "equipment_database.csv"
        records = location_agg.get("all_equipment", [])
        self.store.save_csv(str(path), records)
        print(f"  [csv] written {path} ({len(records)} equipment items)")
        return path

    # ------------------------------------------------------------------
    # knowledge_index.csv
    # ------------------------------------------------------------------

    def write_knowledge(
        self,
        out_dir: str | Path,
        knowledge_agg: dict,
    ) -> Path:
        out_dir = Path(out_dir)
        path = out_dir / "knowledge_index.csv"

        raw_items = knowledge_agg.get("all_items", [])
        records = []
        for item in raw_items:
            records.append({
                "video_id": item.get("video_id", ""),
                "video_title": item.get("video_title", ""),
                "video_url": item.get("video_url", ""),
                "published_at": item.get("published_at", ""),
                "category_zh": item.get("category_zh", item.get("category", "")),
                "topic_zh": item.get("topic_zh", item.get("topic", "")),
                "summary": item.get("summary", ""),
                "original_excerpt": item.get("original_excerpt", ""),
                "difficulty_level": item.get("difficulty_level", ""),
                "tags": ", ".join(item.get("tags", [])),
            })

        self.store.save_csv(str(path), records)
        print(f"  [csv] written {path} ({len(records)} knowledge items)")
        return path

    # ------------------------------------------------------------------
    # Convenience: write all location-related CSVs at once
    # ------------------------------------------------------------------

    def write_all_location_csvs(
        self,
        out_dir: str | Path,
        location_agg: dict,
    ) -> list[Path]:
        return [
            self.write_locations(out_dir, location_agg),
            self.write_food(out_dir, location_agg),
            self.write_equipment(out_dir, location_agg),
        ]
