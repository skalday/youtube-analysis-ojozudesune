from datetime import datetime, timezone

from analyzers.claude_client import ClaudeClient

SYSTEM_PROMPT = """You are a professional golf knowledge organiser responsible for accurately extracting knowledge points and tips from Japanese YouTube golf video transcripts.
Write summaries in English, preserving original Japanese excerpts.
Output must be valid JSON with no extra text.
If an episode has no clear knowledge points or tips, return an empty array [] for knowledge_items."""

EXTRACTION_PROMPT_TEMPLATE = """Below is the transcript of a YouTube video:

Video title: {title}
Video URL: https://youtu.be/{video_id}
Published date: {published_at}

Transcript:
{transcript_text}

Extract all golf knowledge points and tips from the transcript and output the following JSON:

{{
  "video_id": "{video_id}",
  "video_title": "{title}",
  "video_url": "https://youtu.be/{video_id}",
  "published_at": "{published_at}",
  "episode_summary": "Summary of the main content of this episode (English, 2-3 sentences)",
  "knowledge_items": [
    {{
      "category": "Knowledge category (choose one: スイング技術/コース戦略/メンタル/練習方法/ルール・マナー/クラブ選択/コース紹介/その他)",
      "category_en": "Category in English (swing_technique/course_strategy/mental/practice_method/rules_etiquette/club_selection/course_intro/other)",
      "topic": "Knowledge point title (original Japanese or English)",
      "topic_en": "Knowledge point title (English)",
      "summary": "Detailed explanation (English, 3-5 sentences, understandable without knowledge of Japanese)",
      "original_excerpt": "Most relevant original transcript excerpt (1-3 sentences in Japanese)",
      "difficulty_level": "Difficulty level (beginner/intermediate/advanced, based on content)",
      "tags": ["Related tags, e.g. driver, approach, bunker, etc."]
    }}
  ]
}}

Category descriptions:
- スイング技術 (swing_technique): Swing motion, posture, grip, angles and other technical points
- コース戦略 (course_strategy): Club selection, wind reading, fairway planning, target selection
- メンタル (mental): Mental adjustment, pressure management, focus
- 練習方法 (practice_method): Range training, specific practice drills, improvement methods
- ルール・マナー (rules_etiquette): Golf rules, course etiquette, notes
- クラブ選択 (club_selection): Club characteristics, selection advice, reviews
- コース紹介 (course_intro): Features, challenges, and strategies of specific courses
- その他 (other): Knowledge not fitting the above categories"""

# Prompt for generating the cross-video knowledge index
INDEX_SYNTHESIS_PROMPT = """Below are knowledge extraction results from {video_count} golf YouTube videos:

{items_text}

Compile a cross-video knowledge index summary and output the following JSON:
{{
  "total_knowledge_items": total number of knowledge items (integer),
  "category_breakdown": {{
    "swing_technique": count,
    "course_strategy": count,
    "mental": count,
    "practice_method": count,
    "rules_etiquette": count,
    "club_selection": count,
    "course_intro": count,
    "other": count
  }},
  "top_topics": ["Most frequent or most important knowledge topics, list 5-10 items (English)"],
  "learning_path_suggestion": "Suggested learning order based on the content (English, 2-3 sentences)"
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

        for video in tqdm(videos, desc="Extracting golf knowledge", unit="vid"):
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
                "by_category": {...},  # grouped by category_en
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

                cat = item.get("category_en", item.get("category", "other"))
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
                f"[{item.get('category_en', item.get('category', 'other'))}] "
                f"{item.get('topic_en', item.get('topic', ''))} "
                f"-- {item.get('summary', '')[:80]}"
            )

        items_text = "\n".join(lines)
        prompt = INDEX_SYNTHESIS_PROMPT.format(
            video_count=len(all_results),
            items_text=items_text,
        )

        result = self.client.analyze_json(SYSTEM_PROMPT, prompt)
        return result or {}
