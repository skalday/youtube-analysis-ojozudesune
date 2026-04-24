from datetime import datetime, timezone

from modules.llm_providers.base import BaseLLMClient

SYSTEM_PROMPT = """You are a professional personal brand strategy consultant specialising in analysing YouTube video transcripts to determine creator brand positioning.
Analyse the provided transcript data in depth. Output in English.
Output must be valid JSON with no extra text."""

ANALYSIS_PROMPT_TEMPLATE = """Below are transcripts from {video_count} videos on the YouTube channel "{channel_title}" (sorted by view count descending):

{transcripts_text}

Analyse these transcripts and output the following JSON structure:

{{
  "content_themes": [
    {{
      "theme": "Theme name",
      "description": "Theme description",
      "frequency": "Frequency (high/medium/low)"
    }}
  ],
  "tone_of_voice": "Overall tone description (e.g. casual and friendly, authoritative, instructional)",
  "communication_style": "Detailed communication style description (pace, vocabulary, interaction style)",
  "value_propositions": ["Core values the channel delivers to viewers, 3-5 items"],
  "unique_differentiators": ["Points of differentiation from similar channels, 3-5 items"],
  "target_message": "The core message the channel wants viewers to remember (1-2 sentences)",
  "brand_personality": ["Adjectives describing the brand personality, 5-8 items"],
  "content_gaps": ["Areas where current content could be strengthened, 2-3 items"],
  "key_insights": ["3-5 most important brand insights"]
}}"""

MULTI_CHUNK_SYNTHESIS_PROMPT = """You have analysed multiple batches of transcripts. Below are the analysis results from each batch:

{partial_results}

Synthesise all the above analyses into a single consolidated brand positioning JSON (same format as above, no duplicate items, output in English)."""


def _format_transcripts(transcripts: dict, videos: list, max_chars: int = 80_000) -> tuple:
    view_lookup = {v["video_id"]: v.get("view_count", 0) for v in videos}
    title_lookup = {v["video_id"]: v["title"] for v in videos}

    items = []
    for video_id, transcript in transcripts.items():
        if transcript and transcript.get("full_text"):
            items.append({
                "video_id": video_id,
                "title": title_lookup.get(video_id, video_id),
                "view_count": view_lookup.get(video_id, 0),
                "text": transcript["full_text"],
            })

    items.sort(key=lambda x: x["view_count"], reverse=True)

    lines = []
    total_chars = 0
    count = 0
    for item in items:
        header = f"\n=== [{item['title']}] (views: {item['view_count']:,}) ===\n"
        body = item["text"]
        if total_chars + len(header) + len(body) > max_chars:
            remaining = max_chars - total_chars - len(header) - 100
            if remaining > 500:
                lines.append(header + body[:remaining] + "...(truncated)")
                count += 1
            break
        lines.append(header + body)
        total_chars += len(header) + len(body)
        count += 1

    return "\n".join(lines), count


class BrandAnalyzer:
    def __init__(self, client: BaseLLMClient):
        self.client = client

    def analyze(self, transcripts: dict, videos: list, channel_title: str = "") -> dict:
        """Analyze transcripts across multiple videos for brand positioning."""
        transcripts_text, video_count = _format_transcripts(transcripts, videos)

        if video_count == 0:
            return {"error": "No transcripts available for analysis"}

        chunks = self.client.chunk_texts([transcripts_text])

        if len(chunks) == 1:
            prompt = ANALYSIS_PROMPT_TEMPLATE.format(
                channel_title=channel_title or "(unknown channel)",
                video_count=video_count,
                transcripts_text=chunks[0],
            )
            result = self.client.analyze_json(SYSTEM_PROMPT, prompt)
        else:
            partial_results = []
            for i, chunk in enumerate(chunks, 1):
                prompt = ANALYSIS_PROMPT_TEMPLATE.format(
                    channel_title=channel_title or "(unknown channel)",
                    video_count=video_count,
                    transcripts_text=chunk,
                )
                partial = self.client.analyze(SYSTEM_PROMPT, prompt)
                partial_results.append(f"[Batch {i}]\n{partial}")

            synthesis_prompt = MULTI_CHUNK_SYNTHESIS_PROMPT.format(
                partial_results="\n\n".join(partial_results)
            )
            result = self.client.analyze_json(SYSTEM_PROMPT, synthesis_prompt)

        if result is None:
            raw = self.client.analyze(SYSTEM_PROMPT,
                ANALYSIS_PROMPT_TEMPLATE.format(
                    channel_title=channel_title or "(unknown channel)",
                    video_count=video_count,
                    transcripts_text=transcripts_text[:50000],
                ))
            result = {"raw_analysis": raw}

        result["analysis_date"] = datetime.now(timezone.utc).isoformat()
        result["video_count"] = video_count

        return result
