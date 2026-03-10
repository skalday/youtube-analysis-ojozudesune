from datetime import datetime, timezone

from analyzers.claude_client import ClaudeClient

SYSTEM_PROMPT = """You are a professional audience (TA) analyst specialising in deriving audience profiles from YouTube comments.
Analyse the provided comment data in depth. Output in English.
Output must be valid JSON with no extra text or markdown outside the JSON."""

ANALYSIS_PROMPT_TEMPLATE = """Below are comments from {video_count} videos on the YouTube channel "{channel_title}" (total {comment_count} comments, sorted by like count descending):

{comments_text}

Analyse these comments and output the following JSON structure:

{{
  "demographics": {{
    "age_range": "Estimated primary age range (e.g. 25-40)",
    "occupation_types": ["List of inferred occupation types"],
    "location_hints": ["Location clues inferred from language or topics"]
  }},
  "interests": ["Topics or interests viewers care about most, 5-10 items"],
  "pain_points": ["Viewer frustrations, problems, or expectations, 5-10 items"],
  "language_patterns": {{
    "formality": "Description of formality level",
    "common_emojis": ["List of frequently used emojis"],
    "frequent_terms": ["Frequently appearing specific words or expressions"]
  }},
  "engagement_triggers": ["Content types or topics that generate the most comments or likes, 3-5 items"],
  "sentiment_breakdown": {{
    "positive": positive comment ratio (float 0.0-1.0),
    "neutral": neutral comment ratio,
    "negative": negative comment ratio
  }},
  "key_insights": ["3-5 most important audience insights"],
  "recommended_content_directions": ["Recommended content directions based on audience analysis, 3-5 items"]
}}"""


def _format_comments(all_comments: dict, videos: list, max_total: int = 3000) -> tuple:
    """
    Flatten and sort comments by like_count descending.
    Returns (formatted_text, total_count, video_count_with_comments)
    """
    # Build video title lookup
    title_lookup = {v["video_id"]: v["title"] for v in videos}

    flat = []
    for video_id, comments in all_comments.items():
        title = title_lookup.get(video_id, video_id)
        for c in comments:
            flat.append({
                "video_title": title,
                "text": c.get("text", ""),
                "like_count": c.get("like_count", 0),
            })

    # Sort by likes descending, take top max_total
    flat.sort(key=lambda x: x["like_count"], reverse=True)
    flat = flat[:max_total]

    lines = []
    for item in flat:
        likes = item["like_count"]
        like_str = f"[likes:{likes}] " if likes > 0 else ""
        lines.append(f"[{item['video_title']}] {like_str}{item['text']}")

    videos_with_comments = sum(1 for v in all_comments.values() if v)
    return "\n".join(lines), len(flat), videos_with_comments


class AudienceAnalyzer:
    def __init__(self, client: ClaudeClient):
        self.client = client

    def analyze(self, all_comments: dict, videos: list, channel_title: str = "") -> dict:
        """
        Analyze comments across multiple videos to build TA profile.

        Args:
            all_comments: {video_id: [comment_dict, ...]}
            videos: list of video metadata dicts
            channel_title: display name of the channel

        Returns:
            TA profile dict
        """
        comments_text, total_count, video_count = _format_comments(all_comments, videos)

        if total_count == 0:
            return {"error": "No comments available for analysis"}

        prompt = ANALYSIS_PROMPT_TEMPLATE.format(
            channel_title=channel_title or "(unknown channel)",
            video_count=video_count,
            comment_count=total_count,
            comments_text=comments_text,
        )

        result = self.client.analyze_json(SYSTEM_PROMPT, prompt)

        if result is None:
            # Fallback: return raw text
            raw = self.client.analyze(SYSTEM_PROMPT, prompt)
            result = {"raw_analysis": raw}

        result["analysis_date"] = datetime.now(timezone.utc).isoformat()
        result["video_count"] = video_count
        result["comment_count"] = total_count

        return result
