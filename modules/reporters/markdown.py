from __future__ import annotations

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

    def write_audience_report(self, out_dir: str | Path, audience: dict, channel_title: str) -> Path:
        out_dir = Path(out_dir)
        path = out_dir / "audience_report.md"

        demo = audience.get("demographics", {})
        lang = audience.get("language_patterns", {})
        sentiment = audience.get("sentiment_breakdown", {})

        pos = sentiment.get("positive", 0)
        neu = sentiment.get("neutral", 0)
        neg = sentiment.get("negative", 0)

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
            f"Positive {pos:.0%} / Neutral {neu:.0%} / Negative {neg:.0%}",
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

    def write_brand_report(self, out_dir: str | Path, brand: dict, channel_title: str) -> Path:
        out_dir = Path(out_dir)
        path = out_dir / "brand_report.md"

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
            lines += ["", "---", "", "## Raw Analysis (fallback)", "", "```",
                      brand["raw_analysis"], "```"]

        _write(path, "\n".join(lines))
        return path

