from datetime import datetime, timezone

from analyzers.claude_client import ClaudeClient

SYSTEM_PROMPT = """你是一位專業的個人品牌策略顧問，擅長從 YouTube 影片逐字稿中分析創作者的品牌定位。
請根據提供的逐字稿資料進行深度分析，所有輸出請使用繁體中文。
輸出必須是合法的 JSON 格式，不要加入任何說明文字。"""

ANALYSIS_PROMPT_TEMPLATE = """以下是 YouTube 頻道「{channel_title}」的 {video_count} 支影片逐字稿（依觀看數排序）：

{transcripts_text}

請分析這些逐字稿，輸出以下 JSON 結構（請用繁體中文填寫所有文字欄位）：

{{
  "content_themes": [
    {{
      "theme": "主題名稱",
      "description": "主題描述",
      "frequency": "出現頻率（高/中/低）"
    }}
  ],
  "tone_of_voice": "整體語調描述（例：輕鬆親切、專業權威、教學引導型）",
  "communication_style": "溝通風格詳細描述（包含說話節奏、用詞特色、互動方式）",
  "value_propositions": ["頻道向觀眾傳遞的核心價值，列出3-5條"],
  "unique_differentiators": ["與同類型頻道相比的差異化特點，列出3-5條"],
  "target_message": "頻道希望觀眾最終記住的核心訊息（1-2句話）",
  "brand_personality": ["描述品牌個性的形容詞，5-8個"],
  "content_gaps": ["目前內容中可以補強的方向，2-3條"],
  "key_insights": ["3-5條最重要的品牌洞察"]
}}"""

MULTI_CHUNK_SYNTHESIS_PROMPT = """你已經分析了多批逐字稿，以下是各批次的分析結果：

{partial_results}

請綜合以上所有分析，輸出一份統整的品牌定位 JSON（格式同上，不要重複列出相同項目，請用繁體中文）。"""


def _format_transcripts(transcripts: dict, videos: list, max_chars: int = 80_000) -> tuple:
    """
    Format transcripts sorted by view_count descending.
    Returns (formatted_text, video_count_with_transcripts)
    """
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
        header = f"\n=== 【{item['title']}】（觀看數：{item['view_count']:,}）===\n"
        body = item["text"]
        if total_chars + len(header) + len(body) > max_chars:
            # Truncate last item to fit
            remaining = max_chars - total_chars - len(header) - 100
            if remaining > 500:
                lines.append(header + body[:remaining] + "…（已截斷）")
                count += 1
            break
        lines.append(header + body)
        total_chars += len(header) + len(body)
        count += 1

    return "\n".join(lines), count


class BrandAnalyzer:
    def __init__(self, client: ClaudeClient):
        self.client = client

    def analyze(self, transcripts: dict, videos: list, channel_title: str = "") -> dict:
        """
        Analyze transcripts across multiple videos for brand positioning.

        Args:
            transcripts: {video_id: transcript_dict_or_None}
            videos: list of video metadata dicts
            channel_title: display name of the channel

        Returns:
            Brand positioning dict
        """
        transcripts_text, video_count = _format_transcripts(transcripts, videos)

        if video_count == 0:
            return {"error": "No transcripts available for analysis"}

        # Check if text fits in one chunk
        chunks = self.client.chunk_texts([transcripts_text])

        if len(chunks) == 1:
            prompt = ANALYSIS_PROMPT_TEMPLATE.format(
                channel_title=channel_title or "（未知頻道）",
                video_count=video_count,
                transcripts_text=chunks[0],
            )
            result = self.client.analyze_json(SYSTEM_PROMPT, prompt)
        else:
            # Multi-chunk: analyze each, then synthesize
            partial_results = []
            for i, chunk in enumerate(chunks, 1):
                prompt = ANALYSIS_PROMPT_TEMPLATE.format(
                    channel_title=channel_title or "（未知頻道）",
                    video_count=video_count,
                    transcripts_text=chunk,
                )
                partial = self.client.analyze(SYSTEM_PROMPT, prompt)
                partial_results.append(f"【第{i}批分析】\n{partial}")

            synthesis_prompt = MULTI_CHUNK_SYNTHESIS_PROMPT.format(
                partial_results="\n\n".join(partial_results)
            )
            result = self.client.analyze_json(SYSTEM_PROMPT, synthesis_prompt)

        if result is None:
            raw = self.client.analyze(SYSTEM_PROMPT,
                ANALYSIS_PROMPT_TEMPLATE.format(
                    channel_title=channel_title or "（未知頻道）",
                    video_count=video_count,
                    transcripts_text=transcripts_text[:50000],
                ))
            result = {"raw_analysis": raw}

        result["analysis_date"] = datetime.now(timezone.utc).isoformat()
        result["video_count"] = video_count

        return result
