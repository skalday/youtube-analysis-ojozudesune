import csv
import json
import os
import tempfile


class FileStore:
    def __init__(self, base_dir: str):
        self.base_dir = base_dir

    def _ensure_dir(self, path: str):
        os.makedirs(os.path.dirname(path), exist_ok=True)

    def save_json(self, path: str, data) -> None:
        """Atomic write JSON with UTF-8 encoding."""
        self._ensure_dir(path)
        dir_name = os.path.dirname(path)
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", delete=False,
            dir=dir_name, suffix=".tmp"
        ) as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            tmp_path = f.name
        os.replace(tmp_path, path)

    def load_json(self, path: str):
        """Return None if file does not exist."""
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def save_csv(self, path: str, records: list) -> None:
        """Write list of dicts to CSV with UTF-8-sig for Excel compatibility."""
        if not records:
            return
        self._ensure_dir(path)
        fieldnames = list(records[0].keys())
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(records)

    def load_csv(self, path: str) -> list:
        if not os.path.exists(path):
            return []
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f))

    def exists(self, path: str) -> bool:
        return os.path.exists(path)

    # --- Path builders ---

    def video_list_path(self, channel_id: str) -> str:
        return os.path.join(self.base_dir, "raw", "videos", channel_id, "video_list.json")

    def transcript_path(self, channel_id: str, video_id: str) -> str:
        return os.path.join(self.base_dir, "raw", "transcripts", channel_id, f"{video_id}.json")

    def comments_path(self, channel_id: str, video_id: str) -> str:
        return os.path.join(self.base_dir, "raw", "comments", channel_id, f"{video_id}.json")

    def analysis_path(self, channel_id: str, analysis_type: str) -> str:
        return os.path.join(
            self.base_dir, "processed", analysis_type, channel_id, "result.json"
        )
