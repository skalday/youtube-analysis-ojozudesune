"""
MarkdownReporter — 產生人類可讀的 Markdown 分析報告。
"""
from __future__ import annotations

import os
from pathlib import Path


def _bullet_list(items: list) -> str:
    if not items:
        return "_（無資料）_\n"
    return "\n".join(f"- {item}" for item in items) + "\n"


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"  [markdown] 已寫入 {path}")


class MarkdownReporter:
    # ------------------------------------------------------------------
    # audience_report.md
    # ------------------------------------------------------------------

    def write_audience_report(
        self,
        out_dir: str | Path,
        audience: dict,
        channel_title: str,
    ) -> Path:
        out_dir = Path(out_dir)
        path = out_dir / "audience_report.md"

        demo = audience.get("demographics", {})
        lang = audience.get("language_patterns", {})
        sentiment = audience.get("sentiment_breakdown", {})

        pos = sentiment.get("positive", 0)
        neu = sentiment.get("neutral", 0)
        neg = sentiment.get("negative", 0)
        sentiment_bar = (
            f"正面 {pos:.0%} ／ 中性 {neu:.0%} ／ 負面 {neg:.0%}"
        )

        lines = [
            f"# TA 輪廓分析報告 — {channel_title}",
            "",
            f"> 分析日期：{audience.get('analysis_date', 'N/A')}　｜　"
            f"分析影片數：{audience.get('video_count', 0)}　｜　"
            f"分析留言數：{audience.get('comment_count', 0)}",
            "",
            "---",
            "",
            "## 人口特徵",
            "",
            f"- **推估年齡層**：{demo.get('age_range', 'N/A')}",
            f"- **職業類型**：{', '.join(demo.get('occupation_types', [])) or 'N/A'}",
            f"- **地區推斷**：{', '.join(demo.get('location_hints', [])) or 'N/A'}",
            "",
            "## 興趣與關注點",
            "",
            _bullet_list(audience.get("interests", [])),
            "## 痛點與需求",
            "",
            _bullet_list(audience.get("pain_points", [])),
            "## 語言習慣",
            "",
            f"- **敬語程度**：{lang.get('formality', 'N/A')}",
            f"- **常用詞彙**：{', '.join(lang.get('frequent_terms', [])) or 'N/A'}",
            f"- **常用表情符號**：{' '.join(lang.get('common_emojis', [])) or 'N/A'}",
            "",
            "## 互動觸發點",
            "",
            _bullet_list(audience.get("engagement_triggers", [])),
            "## 情感傾向分布",
            "",
            sentiment_bar,
            "",
            "## 關鍵洞察",
            "",
            _bullet_list(audience.get("key_insights", [])),
            "## 建議內容方向",
            "",
            _bullet_list(audience.get("recommended_content_directions", [])),
        ]

        if audience.get("error"):
            lines.insert(4, f"\n> **⚠️ 警告**：{audience['error']}\n")

        _write(path, "\n".join(lines))
        return path

    # ------------------------------------------------------------------
    # brand_report.md
    # ------------------------------------------------------------------

    def write_brand_report(
        self,
        out_dir: str | Path,
        brand: dict,
        channel_title: str,
    ) -> Path:
        out_dir = Path(out_dir)
        path = out_dir / "brand_report.md"

        # Core content themes table
        themes = brand.get("content_themes", [])
        if themes and isinstance(themes[0], dict):
            theme_rows = ["| 主題 | 說明 | 出現頻率 |", "|------|------|---------|"]
            for t in themes:
                theme_rows.append(
                    f"| {t.get('theme','')} | {t.get('description','')} | {t.get('frequency','')} |"
                )
            themes_block = "\n".join(theme_rows) + "\n"
        else:
            themes_block = _bullet_list([str(t) for t in themes])

        lines = [
            f"# 品牌定位分析報告 — {channel_title}",
            "",
            f"> 分析日期：{brand.get('analysis_date', 'N/A')}　｜　"
            f"分析影片數：{brand.get('video_count', 0)}",
            "",
            "---",
            "",
            "## 核心內容主題",
            "",
            themes_block,
            "## 溝通風格與語調",
            "",
            f"**語調**：{brand.get('tone_of_voice', 'N/A')}",
            "",
            f"**風格**：{brand.get('communication_style', 'N/A')}",
            "",
            "## 價值主張",
            "",
            _bullet_list(brand.get("value_propositions", [])),
            "## 差異化定位",
            "",
            _bullet_list(brand.get("unique_differentiators", [])),
            "## 品牌個性",
            "",
            ", ".join(brand.get("brand_personality", [])) or "_（無資料）_",
            "",
            "## 核心訊息",
            "",
            brand.get("target_message", "_（無資料）_"),
            "",
            "## 內容缺口",
            "",
            _bullet_list(brand.get("content_gaps", [])),
            "## 關鍵洞察",
            "",
            _bullet_list(brand.get("key_insights", [])),
        ]

        if brand.get("raw_analysis"):
            lines += [
                "",
                "---",
                "",
                "## 原始分析文字（備用）",
                "",
                "```",
                brand["raw_analysis"],
                "```",
            ]

        _write(path, "\n".join(lines))
        return path

    # ------------------------------------------------------------------
    # knowledge_index.md
    # ------------------------------------------------------------------

    def write_knowledge_index(
        self,
        out_dir: str | Path,
        knowledge_agg: dict,
        channel_title: str,
    ) -> Path:
        out_dir = Path(out_dir)
        path = out_dir / "knowledge_index.md"

        stats = knowledge_agg.get("stats", {})
        index_summary = knowledge_agg.get("index_summary", {})
        by_category = knowledge_agg.get("by_category", {})
        extraction_date = knowledge_agg.get("extraction_date", "N/A")

        lines = [
            f"# 高爾夫知識索引 — {channel_title}",
            "",
            f"> 提取日期：{extraction_date[:10]}　｜　"
            f"處理影片數：{stats.get('videos_processed', 0)}　｜　"
            f"知識點總數：{stats.get('total_knowledge_items', 0)}",
            "",
            "---",
            "",
        ]

        # Learning path
        if index_summary.get("learning_path_suggestion"):
            lines += [
                "## 學習路徑建議",
                "",
                index_summary["learning_path_suggestion"],
                "",
            ]

        # Top topics
        top_topics = index_summary.get("top_topics", [])
        if top_topics:
            lines += [
                "## 重點主題",
                "",
                _bullet_list(top_topics),
            ]

        lines += ["---", ""]

        # Category order
        category_order = [
            "揮桿技術", "球場策略", "練習方法",
            "心理技巧", "球桿選擇", "球場介紹",
            "規則禮儀", "其他",
        ]
        # Add any extra categories not in predefined order
        for cat in by_category:
            if cat not in category_order:
                category_order.append(cat)

        for cat in category_order:
            items = by_category.get(cat)
            if not items:
                continue

            lines += [
                f"## {cat}（{len(items)} 個知識點）",
                "",
                "| 主題 | 摘要 | 難易度 | 影片來源 |",
                "|------|------|--------|---------|",
            ]

            for item in items:
                topic = item.get("topic_zh", item.get("topic", ""))
                summary = item.get("summary", "")
                # Truncate long summaries in table
                if len(summary) > 60:
                    summary = summary[:57] + "..."
                difficulty = item.get("difficulty_level", "")
                video_title = item.get("video_title", "")
                video_url = item.get("video_url", "")
                source = f"[{video_title[:20]}]({video_url})" if video_url else video_title[:20]

                # Escape pipes in table cells
                topic = topic.replace("|", "｜")
                summary = summary.replace("|", "｜")

                lines.append(f"| {topic} | {summary} | {difficulty} | {source} |")

            lines.append("")

        _write(path, "\n".join(lines))
        return path
