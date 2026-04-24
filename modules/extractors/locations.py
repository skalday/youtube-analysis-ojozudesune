from datetime import datetime, timezone

from modules.llm_providers.base import BaseLLMClient

SYSTEM_PROMPT = """You are a professional data extractor responsible for accurately extracting location, food, and equipment information from Japanese YouTube golf video transcripts.
Output must be valid JSON with no extra text.
If an episode has no relevant information, return empty arrays [] for the corresponding fields."""

EXTRACTION_PROMPT_TEMPLATE = """Below is the transcript of a YouTube video:

Video title: {title}
Video URL: https://youtu.be/{video_id}
Published date: {published_at}

Transcript:
{transcript_text}

Extract the following information from the transcript and output JSON:

{{
  "video_id": "{video_id}",
  "video_title": "{title}",
  "video_url": "https://youtu.be/{video_id}",
  "published_at": "{published_at}",
  "locations": [
    {{
      "name": "Location name (original text)",
      "name_zh": "Location name (English translation, or same if already English)",
      "city": "City or prefecture",
      "type": "Type (golf_course / driving_range / restaurant / hotel / other)",
      "context": "Original transcript excerpt mentioning this location (1-2 sentences)"
    }}
  ],
  "food": [
    {{
      "name": "Food or drink name (original text)",
      "name_zh": "English name",
      "location": "Where it was consumed (e.g. clubhouse, on course, not mentioned)",
      "context": "Original transcript excerpt"
    }}
  ],
  "equipment": [
    {{
      "type": "Equipment type (driver / iron / wedge / putter / ball / bag / shoes / apparel / other)",
      "brand": "Brand name",
      "model": "Model name (if mentioned)",
      "context": "Original transcript excerpt"
    }}
  ]
}}"""


class LocationExtractor:
    def __init__(self, client: BaseLLMClient):
        self.client = client

    def extract_one(self, video: dict, transcript: dict) -> dict:
        """Extract locations, food, equipment from a single video transcript."""
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
                "locations": [],
                "food": [],
                "equipment": [],
                "skipped": True,
            }

        prompt = EXTRACTION_PROMPT_TEMPLATE.format(
            video_id=video_id,
            title=title,
            published_at=published_at,
            transcript_text=transcript_text[:25_000],
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
        """Extract from multiple videos."""
        from tqdm import tqdm

        skip = skip_existing or set()
        results = []

        for video in tqdm(videos, desc="Extracting locations/food/equipment", unit="vid"):
            video_id = video["video_id"]
            if video_id in skip:
                continue
            transcript = transcripts.get(video_id)
            results.append(self.extract_one(video, transcript))

        return results

    def aggregate(self, all_results: list) -> dict:
        """Aggregate per-video results into flat lists for database export."""
        all_locations = []
        all_food = []
        all_equipment = []

        for result in all_results:
            video_id = result.get("video_id", "")
            video_title = result.get("video_title", "")
            video_url = result.get("video_url", f"https://youtu.be/{video_id}")
            published_at = result.get("published_at", "")

            for loc in result.get("locations", []):
                all_locations.append({"video_id": video_id, "video_title": video_title,
                                      "video_url": video_url, "published_at": published_at, **loc})
            for food in result.get("food", []):
                all_food.append({"video_id": video_id, "video_title": video_title,
                                 "video_url": video_url, "published_at": published_at, **food})
            for equip in result.get("equipment", []):
                all_equipment.append({"video_id": video_id, "video_title": video_title,
                                      "video_url": video_url, "published_at": published_at, **equip})

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
