"""
High-level analysis orchestration.

Usage:
    from modules.analyzer import ChannelAnalyzer
    from modules.llm_providers.local_llm import LocalLLMClient

    llm = LocalLLMClient()
    analyzer = ChannelAnalyzer(llm=llm, data_dir="./data", out_dir="./reports/UCxxx")
    analyzer.analyze(channel_id, channel_title, videos, transcripts, comments)
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from modules.llm_providers.base import BaseLLMClient
from modules.analysis.audience import AudienceAnalyzer
from modules.analysis.brand import BrandAnalyzer
from modules.reporters.markdown import MarkdownReporter
from modules.reporters.csv_reporter import CSVReporter
from modules.storage.file_store import FileStore


class ChannelAnalyzer:
    def __init__(self, llm: BaseLLMClient, data_dir: str | Path, out_dir: str | Path):
        self.llm = llm
        self.data_dir = Path(data_dir)
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)

        store = FileStore(base_dir=str(data_dir))
        self.md = MarkdownReporter()
        self.cr = CSVReporter(store=store)

    def analyze(
        self,
        channel_id: str,
        channel_title: str,
        videos: list,
        transcripts: dict,
        all_comments: dict,
        skip_audience: bool = False,
        skip_brand: bool = False,
        max_videos: int | None = None,
    ) -> list[Path]:
        """Run LLM analysis and write all reports. Returns list of written files."""
        if max_videos:
            videos = videos[:max_videos]
            allowed = {v["video_id"] for v in videos}
            transcripts = {k: v for k, v in transcripts.items() if k in allowed}
            all_comments = {k: v for k, v in all_comments.items() if k in allowed}

        audience_result: dict = {}
        if not skip_audience and all_comments:
            print("\n>>> Audience analysis...")
            try:
                audience_result = AudienceAnalyzer(client=self.llm).analyze(
                    all_comments=all_comments, videos=videos, channel_title=channel_title,
                )
                print(f"    {audience_result.get('comment_count', 0)} comments analysed")
            except Exception as exc:
                print(f"[WARNING] Audience analysis failed: {exc}", file=sys.stderr)
        else:
            print("\n>>> Skipping audience analysis")

        brand_result: dict = {}
        if not skip_brand and transcripts:
            print("\n>>> Brand analysis...")
            try:
                brand_result = BrandAnalyzer(client=self.llm).analyze(
                    transcripts=transcripts, videos=videos, channel_title=channel_title,
                )
                print(f"    {brand_result.get('video_count', 0)} videos analysed")
            except Exception as exc:
                print(f"[WARNING] Brand analysis failed: {exc}", file=sys.stderr)
        else:
            print("\n>>> Skipping brand analysis")

        return self._write_reports(
            channel_id, channel_title, videos, all_comments, transcripts,
            audience_result, brand_result,
        )

    def _store(self) -> FileStore:
        return FileStore(base_dir=str(self.data_dir))

    def _write_summary(
        self,
        channel_id: str,
        channel_title: str,
        videos: list,
        audience: dict,
        brand: dict,
    ) -> Path:
        """Write summary.json used by the web UI to display results."""
        path = self.out_dir / "summary.json"
        now = datetime.now(timezone.utc).isoformat()

        stats = {
            "total_videos": len(videos),
            "videos_with_transcript": sum(1 for v in videos if v.get("has_transcript", False)),
            "total_comments_analyzed": audience.get("comment_count", 0),
        }

        existing = self._store().load_json(str(path)) or {}
        history: list = existing.get("analysis_history", [])
        history.append({"timestamp": now, "stats": stats})

        summary = {
            "channel_id": channel_id,
            "channel_title": channel_title,
            "last_updated": now,
            "stats": stats,
            "analysis_history": history,
        }

        path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f"  [summary] written {path}")
        return path

    def _write_reports(
        self,
        channel_id: str,
        channel_title: str,
        videos: list,
        all_comments: dict,
        transcripts: dict,
        audience_result: dict,
        brand_result: dict,
    ) -> list[Path]:
        print(f"\n>>> Writing reports → {self.out_dir}")
        written: list[Path] = []

        def _try(fn, label):
            try:
                result = fn()
                if result:
                    if isinstance(result, list):
                        written.extend(result)
                    else:
                        written.append(result)
            except Exception as exc:
                print(f"[WARNING] {label}: {exc}", file=sys.stderr)

        if audience_result:
            _try(lambda: self.md.write_audience_report(self.out_dir, audience_result, channel_title), "audience_report.md")
        if brand_result:
            _try(lambda: self.md.write_brand_report(self.out_dir, brand_result, channel_title), "brand_report.md")

        _try(lambda: self._write_summary(
            channel_id=channel_id, channel_title=channel_title, videos=videos,
            audience=audience_result, brand=brand_result,
        ), "summary.json")

        if all_comments:
            _try(lambda: self.cr.write_comments(self.out_dir, all_comments, videos), "comments.csv")
        if transcripts:
            _try(lambda: self.cr.write_transcripts(self.out_dir, transcripts, videos), "transcripts.csv")

        print(f"\n{'='*60}")
        print(f"Done! {len(written)} files written:")
        for p in written:
            print(f"   {p}")
        print(f"{'='*60}\n")

        return written