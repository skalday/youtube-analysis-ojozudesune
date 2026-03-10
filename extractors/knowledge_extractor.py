from datetime import datetime, timezone

from analyzers.claude_client import ClaudeClient

SYSTEM_PROMPT = """你是一位專業的高爾夫知識整理員，負責從日文 YouTube 高爾夫影片逐字稿中精確萃取知識點和技巧。
請用繁體中文撰寫摘要，保留日文原文節錄。
輸出必須是合法的 JSON 格式，不要加入任何說明文字。
若某集沒有明確的知識點或技巧，knowledge_items 請回傳空陣列 []。"""

EXTRACTION_PROMPT_TEMPLATE = """以下是 YouTube 影片的逐字稿：

影片標題：{title}
影片連結：https://youtu.be/{video_id}
發布日期：{published_at}

逐字稿內容：
{transcript_text}

請從逐字稿中萃取所有高爾夫知識點和技巧，輸出以下 JSON：

{{
  "video_id": "{video_id}",
  "video_title": "{title}",
  "video_url": "https://youtu.be/{video_id}",
  "published_at": "{published_at}",
  "episode_summary": "本集主要內容摘要（繁體中文，2-3句）",
  "knowledge_items": [
    {{
      "category": "知識分類（從以下選一：スイング技術/コース戦略/メンタル/練習方法/ルール・マナー/クラブ選択/コース紹介/その他）",
      "category_zh": "分類中文名稱（揮桿技術/球場策略/心理技巧/練習方法/規則禮儀/球桿選擇/球場介紹/其他）",
      "topic": "知識點標題（日文原文或中文）",
      "topic_zh": "知識點標題（繁體中文）",
      "summary": "詳細說明（繁體中文，3-5句，要讓不懂日文的人也能理解重點）",
      "original_excerpt": "逐字稿中最相關的原文節錄（1-3句日文）",
      "difficulty_level": "難易度（初學者/中級/進階，根據內容判斷）",
      "tags": ["相關標籤，例：ドライバー、アプローチ、バンカー等"]
    }}
  ]
}}

分類說明：
- スイング技術（揮桿技術）：揮桿動作、姿勢、握桿、角度等技術要點
- コース戦略（球場策略）：選桿、風向判斷、球道規劃、落點選擇
- メンタル（心理技巧）：心態調整、壓力管理、專注力
- 練習方法（練習方法）：練習場訓練、特定練習法、改善方法
- ルール・マナー（規則禮儀）：高爾夫規則、場地禮儀、注意事項
- クラブ選択（球桿選擇）：球桿特性、選擇建議、評測
- コース紹介（球場介紹）：特定球場的特色、難點、攻略
- その他（其他）：不屬於以上分類的知識"""

# Prompt for generating the cross-video knowledge index
INDEX_SYNTHESIS_PROMPT = """以下是 {video_count} 支高爾夫 YouTube 影片的知識萃取結果：

{items_text}

請整理出一份跨影片的知識索引摘要，輸出以下 JSON：
{{
  "total_knowledge_items": 知識點總數（整數）,
  "category_breakdown": {{
    "揮桿技術": 數量,
    "球場策略": 數量,
    "心理技巧": 數量,
    "練習方法": 數量,
    "規則禮儀": 數量,
    "球桿選擇": 數量,
    "球場介紹": 數量,
    "其他": 數量
  }},
  "top_topics": ["出現最多次或最重要的知識主題，列出5-10項（繁體中文）"],
  "learning_path_suggestion": "根據內容建議的學習順序（繁體中文，2-3句）"
}}"""


class KnowledgeExtractor:
    def __init__(self, client: ClaudeClient):
        self.client = client

    def extract_one(self, video: dict, transcript: dict) -> dict:
        """
        Extract knowledge items from a single video transcript.
        """
        video_id = video["video_id"]
        title = video.get("title", "")
        published_at = video.get("published_at", "")[:10]
        transcript_text = transcript.get("full_text", "") if transcript else ""

        if not transcript_text:
            return {
                "video_id": video_id,
                "video_title": title,
                "video_url": f"https://youtu.be/{video_id}",
                "published_at": published_at,
                "episode_summary": "",
                "knowledge_items": [],
                "skipped": True,
            }

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
                "episode_summary": "",
                "knowledge_items": [],
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
        Extract knowledge from multiple videos.
        """
        from tqdm import tqdm

        skip = skip_existing or set()
        results = []

        for video in tqdm(videos, desc="萃取高爾夫知識", unit="支"):
            video_id = video["video_id"]
            if video_id in skip:
                continue
            transcript = transcripts.get(video_id)
            result = self.extract_one(video, transcript)
            results.append(result)

        return results

    def aggregate(self, all_results: list) -> dict:
        """
        Aggregate per-video results into a flat knowledge database.

        Returns:
            {
                "per_video": [...],
                "all_items": [...],    # flat list, each item has video reference
                "by_category": {...},  # grouped by category_zh
                "index_summary": {...},
                "stats": {...}
            }
        """
        all_items = []
        by_category: dict[str, list] = {}

        for result in all_results:
            video_id = result.get("video_id", "")
            video_title = result.get("video_title", "")
            video_url = result.get("video_url", f"https://youtu.be/{video_id}")
            published_at = result.get("published_at", "")

            for item in result.get("knowledge_items", []):
                flat_item = {
                    "video_id": video_id,
                    "video_title": video_title,
                    "video_url": video_url,
                    "published_at": published_at,
                    **item,
                }
                all_items.append(flat_item)

                cat = item.get("category_zh", item.get("category", "其他"))
                by_category.setdefault(cat, []).append(flat_item)

        # Generate index summary via Claude if we have items
        index_summary = self._generate_index_summary(all_results, all_items)

        return {
            "per_video": all_results,
            "all_items": all_items,
            "by_category": by_category,
            "index_summary": index_summary,
            "extraction_date": datetime.now(timezone.utc).isoformat(),
            "stats": {
                "videos_processed": len(all_results),
                "videos_with_knowledge": sum(
                    1 for r in all_results if r.get("knowledge_items")
                ),
                "total_knowledge_items": len(all_items),
                "category_counts": {
                    cat: len(items) for cat, items in by_category.items()
                },
            },
        }

    def _generate_index_summary(self, all_results: list, all_items: list) -> dict:
        """Generate a summary of the knowledge index using Claude."""
        if not all_items:
            return {}

        # Build compact items text for synthesis
        lines = []
        for item in all_items[:200]:  # Cap to avoid token overflow
            lines.append(
                f"[{item.get('category_zh', '其他')}] "
                f"{item.get('topic_zh', item.get('topic', ''))} "
                f"— {item.get('summary', '')[:80]}"
            )

        items_text = "\n".join(lines)
        prompt = INDEX_SYNTHESIS_PROMPT.format(
            video_count=len(all_results),
            items_text=items_text,
        )

        result = self.client.analyze_json(SYSTEM_PROMPT, prompt)
        return result or {}
