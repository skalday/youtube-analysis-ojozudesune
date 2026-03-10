"""
JSONReporter — 產生 summary.json 整合報告（含累加歷史快照）。
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from storage.file_store import FileStore


class JSONReporter:
    def __init__(self, store: FileStore):
        self.store = store

    def write_summary(
        self,
        out_dir: str | Path,
        channel_id: str,
        channel_title: str,
        videos: list,
        audience: dict,
        brand: dict,
        location_agg: dict | None = None,
        knowledge_agg: dict | None = None,
    ) -> Path:
        """
        Write summary.json with all analysis results.
        Appends a new snapshot to analysis_history[] on each run.
        """
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / "summary.json"

        now = datetime.now(timezone.utc).isoformat()

        # --- Build stats ---
        loc_stats = (location_agg or {}).get("stats", {})
        know_stats = (knowledge_agg or {}).get("stats", {})
        all_comments_count = sum(
            len(v) for v in audience.get("_raw_comment_counts", {}).values()
        ) if "_raw_comment_counts" in audience else audience.get("comment_count", 0)

        stats = {
            "total_videos": len(videos),
            "videos_with_transcript": sum(
                1 for v in videos if v.get("has_transcript", False)
            ),
            "total_comments_analyzed": audience.get("comment_count", 0),
            "total_locations": loc_stats.get("total_locations", 0),
            "unique_golf_courses": loc_stats.get("unique_golf_courses", 0),
            "total_food_items": loc_stats.get("total_food_items", 0),
            "total_equipment_items": loc_stats.get("total_equipment_items", 0),
            "total_knowledge_items": know_stats.get("total_knowledge_items", 0),
        }

        # --- Load existing summary to preserve history ---
        existing = self.store.load_json(str(path)) or {}
        history: list = existing.get("analysis_history", [])
        history.append({"timestamp": now, "stats": stats})

        summary = {
            "channel_id": channel_id,
            "channel_title": channel_title,
            "last_updated": now,
            "stats": stats,
            "audience_analysis": _strip_internal(audience),
            "brand_analysis": _strip_internal(brand),
            "location_stats": loc_stats,
            "knowledge_stats": know_stats,
            "analysis_history": history,
        }

        self.store.save_json(str(path), summary)
        print(f"  [json] 已寫入 {path}")
        return path


def _strip_internal(d: dict) -> dict:
    """Remove internal-only keys (prefixed with _) before saving."""
    return {k: v for k, v in d.items() if not k.startswith("_")}
