from datetime import datetime, timezone

from analyzers.claude_client import ClaudeClient

SYSTEM_PROMPT = """你是一位專業的資料萃取員，負責從日文 YouTube 高爾夫影片逐字稿中精確抽取地點、食物和設備資訊。
輸出必須是合法的 JSON 格式，不要加入任何說明文字。
若某集沒有相關資訊，對應陣列請回傳空陣列 []。"""

EXTRACTION_PROMPT_TEMPLATE = """以下是 YouTube 影片的逐字稿：

影片標題：{title}
影片連結：https://youtu.be/{video_id}
發布日期：{published_at}

逐字稿內容：
{transcript_text}

請從以上逐字稿中萃取以下資訊，輸出 JSON：

{{
  "video_id": "{video_id}",
  "video_title": "{title}",
  "video_url": "https://youtu.be/{video_id}",
  "published_at": "{published_at}",
  "locations": [
    {{
      "name": "地點名稱（原文）",
      "name_zh": "地點名稱（繁體中文翻譯，若已是中文則相同）",
      "city": "所在縣市或都道府縣",
      "type": "類型（golf_course / driving_range / restaurant / hotel / other）",
      "context": "逐字稿中提到此地點的原文節錄（1-2句）"
    }}
  ],
  "food": [
    {{
      "name": "食物或飲料名稱（原文）",
      "name_zh": "繁體中文名稱",
      "location": "在哪裡吃到的（例：クラブハウス、コース内、未提及）",
      "context": "逐字稿原文節錄"
    }}
  ],
  "equipment": [
    {{
      "type": "設備類型（driver / iron / wedge / putter / ball / bag / shoes / apparel / other）",
      "brand": "品牌名稱",
      "model": "型號（若有提及）",
      "context": "逐字稿原文節錄"
    }}
  ]
}}"""


class LocationExtractor:
    def __init__(self, client: ClaudeClient):
        self.client = client

    def extract_one(self, video: dict, transcript: dict) -> dict:
        """
        Extract locations, food, equipment from a single video transcript.

        Args:
            video: video metadata dict (video_id, title, published_at, ...)
            transcript: transcript dict with full_text

        Returns:
            Extraction result dict
        """
        video_id = video["video_id"]
        title = video.get("title", "")
        published_at = video.get("published_at", "")[:10]  # YYYY-MM-DD
        transcript_text = transcript.get("full_text", "") if transcript else ""

        if not transcript_text:
            return {
                "video_id": video_id,
                "video_title": title,
                "video_url": f"https://youtu.be/{video_id}",
                "published_at": published_at,
                "locations": [],
                "food": [],
                "equipment": [],
                "skipped": True,
            }

        # Truncate very long transcripts to avoid token limits
        text_for_prompt = transcript_text[:25_000]

        prompt = EXTRACTION_PROMPT_TEMPLATE.format(
            video_id=video_id,
            title=title,
            published_at=published_at,
            transcript_text=text_for_prompt,
        )

        result = self.client.analyze_json(SYSTEM_PROMPT, prompt)

        if result is None:
            return {
                "video_id": video_id,
                "video_title": title,
                "video_url": f"https://youtu.be/{video_id}",
                "published_at": published_at,
                "locations": [],
                "food": [],
                "equipment": [],
                "error": "JSON parse failed",
            }

        return result

    def extract_batch(
        self,
        videos: list,
        transcripts: dict,
        skip_existing: set | None = None,
    ) -> list:
        """
        Extract from multiple videos.

        Args:
            videos: list of video metadata dicts
            transcripts: {video_id: transcript_dict_or_None}
            skip_existing: set of video_ids already extracted

        Returns:
            List of extraction result dicts
        """
        from tqdm import tqdm

        skip = skip_existing or set()
        results = []

        for video in tqdm(videos, desc="萃取地點/食物/設備", unit="支"):
            video_id = video["video_id"]
            if video_id in skip:
                continue
            transcript = transcripts.get(video_id)
            result = self.extract_one(video, transcript)
            results.append(result)

        return results

    def aggregate(self, all_results: list) -> dict:
        """
        Aggregate per-video results into flat lists for database export.

        Returns:
            {
                "per_video": [...],          # original per-video results
                "all_locations": [...],      # flat list with video reference
                "all_food": [...],
                "all_equipment": [...],
                "stats": {...}
            }
        """
        all_locations = []
        all_food = []
        all_equipment = []

        for result in all_results:
            video_id = result.get("video_id", "")
            video_title = result.get("video_title", "")
            video_url = result.get("video_url", f"https://youtu.be/{video_id}")
            published_at = result.get("published_at", "")

            for loc in result.get("locations", []):
                all_locations.append({
                    "video_id": video_id,
                    "video_title": video_title,
                    "video_url": video_url,
                    "published_at": published_at,
                    **loc,
                })

            for food in result.get("food", []):
                all_food.append({
                    "video_id": video_id,
                    "video_title": video_title,
                    "video_url": video_url,
                    "published_at": published_at,
                    **food,
                })

            for equip in result.get("equipment", []):
                all_equipment.append({
                    "video_id": video_id,
                    "video_title": video_title,
                    "video_url": video_url,
                    "published_at": published_at,
                    **equip,
                })

        return {
            "per_video": all_results,
            "all_locations": all_locations,
            "all_food": all_food,
            "all_equipment": all_equipment,
            "extraction_date": datetime.now(timezone.utc).isoformat(),
            "stats": {
                "videos_processed": len(all_results),
                "total_locations": len(all_locations),
                "total_food_items": len(all_food),
                "total_equipment_items": len(all_equipment),
                "unique_golf_courses": len({
                    loc["name"] for loc in all_locations
                    if loc.get("type") == "golf_course"
                }),
            },
        }
