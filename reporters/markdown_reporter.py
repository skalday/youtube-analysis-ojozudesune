"""
MarkdownReporter — Generate human-readable Markdown analysis reports.
"""
from __future__ import annotations

import os
from pathlib import Path


def _bullet_list(items: list) -> str:
    if not items:
        return "_(no data)_\n"
    return "\n".join(f"- {item}" for item in items) + "\n"


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"  [markdown] written {path}")


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
            f"Positive {pos:.0%} / Neutral {neu:.0%} / Negative {neg:.0%}"
        )

        lines = [
            f"# Audience Profile Report — {channel_title}",
            "",
            f"> Analysis date: {audience.get('analysis_date', 'N/A')}  |  "
            f"Videos analysed: {audience.get('video_count', 0)}  |  "
            f"Comments analysed: {audience.get('comment_count', 0)}",
            "",
            "---",
            "",
            "## Demographics",
            "",
            f"- **Estimated age range**: {demo.get('age_range', 'N/A')}",
            f"- **Occupation types**: {', '.join(demo.get('occupation_types', [])) or 'N/A'}",
            f"- **Location hints**: {', '.join(demo.get('location_hints', [])) or 'N/A'}",
            "",
            "## Interests & Topics",
            "",
            _bullet_list(audience.get("interests", [])),
            "## Pain Points & Needs",
            "",
            _bullet_list(audience.get("pain_points", [])),
            "## Language Patterns",
            "",
            f"- **Formality**: {lang.get('formality', 'N/A')}",
            f"- **Frequent terms**: {', '.join(lang.get('frequent_terms', [])) or 'N/A'}",
            f"- **Common emojis**: {' '.join(lang.get('common_emojis', [])) or 'N/A'}",
            "",
            "## Engagement Triggers",
            "",
            _bullet_list(audience.get("engagement_triggers", [])),
            "## Sentiment Breakdown",
            "",
            sentiment_bar,
            "",
            "## Key Insights",
            "",
            _bullet_list(audience.get("key_insights", [])),
            "## Recommended Content Directions",
            "",
            _bullet_list(audience.get("recommended_content_directions", [])),
        ]

        if audience.get("error"):
            lines.insert(4, f"\n> **Warning**: {audience['error']}\n")

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
            theme_rows = ["| Theme | Description | Frequency |", "|-------|-------------|-----------|"]
            for t in themes:
                theme_rows.append(
                    f"| {t.get('theme','')} | {t.get('description','')} | {t.get('frequency','')} |"
                )
            themes_block = "\n".join(theme_rows) + "\n"
        else:
            themes_block = _bullet_list([str(t) for t in themes])

        lines = [
            f"# Brand Positioning Report — {channel_title}",
            "",
            f"> Analysis date: {brand.get('analysis_date', 'N/A')}  |  "
            f"Videos analysed: {brand.get('video_count', 0)}",
            "",
            "---",
            "",
            "## Core Content Themes",
            "",
            themes_block,
            "## Communication Style & Tone",
            "",
            f"**Tone**: {brand.get('tone_of_voice', 'N/A')}",
            "",
            f"**Style**: {brand.get('communication_style', 'N/A')}",
            "",
            "## Value Propositions",
            "",
            _bullet_list(brand.get("value_propositions", [])),
            "## Unique Differentiators",
            "",
            _bullet_list(brand.get("unique_differentiators", [])),
            "## Brand Personality",
            "",
            ", ".join(brand.get("brand_personality", [])) or "_(no data)_",
            "",
            "## Core Message",
            "",
            brand.get("target_message", "_(no data)_"),
            "",
            "## Content Gaps",
            "",
            _bullet_list(brand.get("content_gaps", [])),
            "## Key Insights",
            "",
            _bullet_list(brand.get("key_insights", [])),
        ]

        if brand.get("raw_analysis"):
            lines += [
                "",
                "---",
                "",
                "## Raw Analysis (fallback)",
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
            f"# Golf Knowledge Index — {channel_title}",
            "",
            f"> Extracted: {extraction_date[:10]}  |  "
            f"Videos processed: {stats.get('videos_processed', 0)}  |  "
            f"Total knowledge items: {stats.get('total_knowledge_items', 0)}",
            "",
            "---",
            "",
        ]

        # Learning path
        if index_summary.get("learning_path_suggestion"):
            lines += [
                "## Suggested Learning Path",
                "",
                index_summary["learning_path_suggestion"],
                "",
            ]

        # Top topics
        top_topics = index_summary.get("top_topics", [])
        if top_topics:
            lines += [
                "## Top Topics",
                "",
                _bullet_list(top_topics),
            ]

        lines += ["---", ""]

        # Category order
        category_order = [
            "swing_technique", "course_strategy", "practice_method",
            "mental", "club_selection", "course_intro",
            "rules_etiquette", "other",
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
                f"## {cat} ({len(items)} items)",
                "",
                "| Topic | Summary | Difficulty | Source |",
                "|-------|---------|------------|--------|",
            ]

            for item in items:
                topic = item.get("topic_en", item.get("topic", ""))
                summary = item.get("summary", "")
                # Truncate long summaries in table
                if len(summary) > 60:
                    summary = summary[:57] + "..."
                difficulty = item.get("difficulty_level", "")
                video_title = item.get("video_title", "")
                video_url = item.get("video_url", "")
                source = f"[{video_title[:20]}]({video_url})" if video_url else video_title[:20]

                # Escape pipes in table cells
                topic = topic.replace("|", "&#124;")
                summary = summary.replace("|", "&#124;")

                lines.append(f"| {topic} | {summary} | {difficulty} | {source} |")

            lines.append("")

        _write(path, "\n".join(lines))
        return path
