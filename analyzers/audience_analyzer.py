from datetime import datetime, timezone

from analyzers.claude_client import ClaudeClient

SYSTEM_PROMPT = """你是一位專業的觀眾受眾（TA）分析師，擅長從 YouTube 留言中洞察受眾輪廓。
請根據提供的留言資料進行深度分析，所有輸出請使用繁體中文。
輸出必須是合法的 JSON 格式，不要加入任何說明文字或 markdown 以外的內容。"""

ANALYSIS_PROMPT_TEMPLATE = """以下是 YouTube 頻道「{channel_title}」的 {video_count} 支影片的留言資料（共 {comment_count} 則，已依按讚數排序）：

{comments_text}

請分析這些留言，輸出以下 JSON 結構（請用繁體中文填寫所有文字欄位）：

{{
  "demographics": {{
    "age_range": "推測的主要年齡層（例：25-40歲）",
    "occupation_types": ["推測的職業類型列表"],
    "location_hints": ["從用語或話題推斷的地區線索"]
  }},
  "interests": ["觀眾最關心的話題或興趣，列出5-10項"],
  "pain_points": ["觀眾的困擾、問題或期待，列出5-10項"],
  "language_patterns": {{
    "formality": "敬語程度描述（例：常用です・ます體，偶爾使用口語）",
    "common_emojis": ["常見表情符號列表"],
    "frequent_terms": ["頻繁出現的特定詞彙或表達方式"]
  }},
  "engagement_triggers": ["哪類內容或話題引發最多留言或高讚，列出3-5項"],
  "sentiment_breakdown": {{
    "positive": 正面留言比例（0.0-1.0的浮點數）,
    "neutral": 中性留言比例,
    "negative": 負面留言比例
  }},
  "key_insights": ["3-5條最重要的受眾洞察"],
  "recommended_content_directions": ["根據受眾分析，建議的內容方向，3-5條"]
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
        like_str = f"[👍{likes}] " if likes > 0 else ""
        lines.append(f"《{item['video_title']}》{like_str}{item['text']}")

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
            channel_title=channel_title or "（未知頻道）",
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
