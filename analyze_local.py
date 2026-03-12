#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Offline analysis script — runs LLM analysis on already-downloaded data.

Usage:
  python analyze_local.py --channel-id UCLs6yOLvSWUyuYF9gyohbiA --llm local
  python analyze_local.py --channel-id UCLs6yOLvSWUyuYF9gyohbiA --llm local --model qwen3:8b
  python analyze_local.py --channel-id UCLs6yOLvSWUyuYF9gyohbiA --llm local --skip-extraction
"""
from __future__ import annotations

import os
import sys
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import argparse
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run LLM analysis on already-downloaded YouTube data (no API required)",
    )
    parser.add_argument("--channel-id", required=True, help="Channel ID (e.g. UCLs6yOLvSWUyuYF9gyohbiA)")
    parser.add_argument("--data-dir", default="./data", help="Base data directory (default: ./data)")
    parser.add_argument("--output-dir", default="./reports", help="Report output directory (default: ./reports)")
    parser.add_argument(
        "--llm", choices=["claude", "local"], default="local",
        help="LLM backend (default: local)",
    )
    parser.add_argument("--model", default=None, help="Model override (e.g. qwen3:8b, gemma3:12b)")
    parser.add_argument("--ollama-url", default="http://localhost:11434/v1", help="Ollama base URL")
    parser.add_argument("--skip-audience", action="store_true", help="Skip audience analysis")
    parser.add_argument("--skip-brand", action="store_true", help="Skip brand analysis")
    parser.add_argument("--skip-extraction", action="store_true", help="Skip location/knowledge extraction")
    parser.add_argument("--max-videos", type=int, default=None, help="Limit number of videos to analyse")
    return parser.parse_args()


def _step(msg: str) -> None:
    print(f"\n>>> {msg}")


def load_videos(data_dir: Path, channel_id: str) -> list:
    path = data_dir / "raw" / "videos" / channel_id / "video_list.json"
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return []


def load_transcripts(data_dir: Path, channel_id: str) -> dict:
    d = data_dir / "raw" / "transcripts" / channel_id
    transcripts = {}
    if not d.exists():
        return transcripts
    for p in d.glob("*.json"):
        with open(p, encoding="utf-8") as f:
            transcripts[p.stem] = json.load(f)
    return transcripts


def load_comments(data_dir: Path, channel_id: str) -> dict:
    d = data_dir / "raw" / "comments" / channel_id
    comments = {}
    if not d.exists():
        return comments
    for p in d.glob("*.json"):
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                comments[p.stem] = data
    return comments


def main() -> None:
    args = parse_args()

    data_dir = Path(args.data_dir)
    out_dir = Path(args.output_dir) / args.channel_id
    out_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    # LLM client                                                           #
    # ------------------------------------------------------------------ #
    if args.llm == "local":
        from analyzers.local_llm_client import LocalLLMClient
        default_model = "qwen3:8b"
        model = args.model or default_model
        llm = LocalLLMClient(model=model, base_url=args.ollama_url)
        print(f"[LLM] local Ollama  model={model}  url={args.ollama_url}")
    else:
        import os
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        if not api_key:
            print("ANTHROPIC_API_KEY not set", file=sys.stderr)
            sys.exit(1)
        from analyzers.claude_client import ClaudeClient
        model = args.model or "claude-sonnet-4-6"
        llm = ClaudeClient(api_key=api_key, model=model)
        print(f"[LLM] Claude API  model={model}")

    # ------------------------------------------------------------------ #
    # Load data from disk                                                  #
    # ------------------------------------------------------------------ #
    _step("Loading video metadata...")
    videos = load_videos(data_dir, args.channel_id)
    if videos:
        channel_title = videos[0].get("channel_title", args.channel_id)
        if args.max_videos:
            videos = videos[: args.max_videos]
        print(f"    {len(videos)} videos  |  channel: {channel_title}")
    else:
        channel_title = args.channel_id
        print("    No video_list.json found; will use video IDs as titles")

    _step("Loading transcripts...")
    transcripts = load_transcripts(data_dir, args.channel_id)
    print(f"    {len(transcripts)} transcript files loaded")

    _step("Loading comments...")
    all_comments = load_comments(data_dir, args.channel_id)
    total_comments = sum(len(c) for c in all_comments.values())
    print(f"    {total_comments} comments across {len(all_comments)} videos")

    # If no video list, build minimal stubs from available data
    if not videos:
        video_ids = set(transcripts) | set(all_comments)
        videos = [{"video_id": vid, "title": vid, "view_count": 0, "is_short": False}
                  for vid in video_ids]

    # Optionally limit to max_videos
    if args.max_videos:
        allowed_ids = {v["video_id"] for v in videos}
        transcripts = {k: v for k, v in transcripts.items() if k in allowed_ids}
        all_comments = {k: v for k, v in all_comments.items() if k in allowed_ids}

    from analyzers.audience_analyzer import AudienceAnalyzer
    from analyzers.brand_analyzer import BrandAnalyzer
    from extractors.location_extractor import LocationExtractor
    from extractors.knowledge_extractor import KnowledgeExtractor
    from reporters.markdown_reporter import MarkdownReporter
    from reporters.json_reporter import JSONReporter
    from reporters.csv_reporter import CSVReporter
    from storage.file_store import FileStore

    store = FileStore(base_dir=str(data_dir))
    md_reporter = MarkdownReporter()
    json_reporter = JSONReporter(store=store)
    csv_reporter = CSVReporter(store=store)

    written: list[Path] = []

    # ------------------------------------------------------------------ #
    # Audience analysis                                                    #
    # ------------------------------------------------------------------ #
    audience_result: dict = {}
    if not args.skip_audience and all_comments:
        _step("Audience analysis...")
        try:
            audience_result = AudienceAnalyzer(client=llm).analyze(
                all_comments=all_comments,
                videos=videos,
                channel_title=channel_title,
            )
            print(f"    Done — {audience_result.get('comment_count', 0)} comments analysed")
        except Exception as exc:
            print(f"    [WARNING] Audience analysis failed: {exc}", file=sys.stderr)
    else:
        print("\n>>> Skipping audience analysis")

    # ------------------------------------------------------------------ #
    # Brand analysis                                                       #
    # ------------------------------------------------------------------ #
    brand_result: dict = {}
    if not args.skip_brand and transcripts:
        _step("Brand analysis...")
        try:
            brand_result = BrandAnalyzer(client=llm).analyze(
                transcripts=transcripts,
                videos=videos,
                channel_title=channel_title,
            )
            print(f"    Done — {brand_result.get('video_count', 0)} videos analysed")
        except Exception as exc:
            print(f"    [WARNING] Brand analysis failed: {exc}", file=sys.stderr)
    else:
        print("\n>>> Skipping brand analysis")

    # ------------------------------------------------------------------ #
    # Location / knowledge extraction                                      #
    # ------------------------------------------------------------------ #
    location_agg: dict = {}
    knowledge_agg: dict = {}
    if not args.skip_extraction and transcripts:
        _step("Extracting locations, food, equipment...")
        try:
            loc_extractor = LocationExtractor(client=llm)
            loc_results = loc_extractor.extract_batch(videos=videos, transcripts=transcripts)
            location_agg = loc_extractor.aggregate(loc_results)
            store.save_json(str(out_dir / "locations_database.json"), location_agg)
            s = location_agg.get("stats", {})
            print(f"    Locations: {s.get('total_locations', 0)}  "
                  f"Food: {s.get('total_food_items', 0)}  "
                  f"Equipment: {s.get('total_equipment_items', 0)}")
        except Exception as exc:
            print(f"    [WARNING] Location extraction failed: {exc}", file=sys.stderr)

        _step("Extracting knowledge index...")
        try:
            know_extractor = KnowledgeExtractor(client=llm)
            know_results = know_extractor.extract_batch(videos=videos, transcripts=transcripts)
            knowledge_agg = know_extractor.aggregate(know_results)
            store.save_json(str(out_dir / "knowledge_index.json"), knowledge_agg)
            s = knowledge_agg.get("stats", {})
            print(f"    {s.get('total_knowledge_items', 0)} knowledge items "
                  f"across {s.get('videos_with_knowledge', 0)} videos")
        except Exception as exc:
            print(f"    [WARNING] Knowledge extraction failed: {exc}", file=sys.stderr)
    else:
        print("\n>>> Skipping extraction")

    # ------------------------------------------------------------------ #
    # Write reports                                                        #
    # ------------------------------------------------------------------ #
    _step(f"Writing reports -> {out_dir}")

    if audience_result:
        try:
            written.append(md_reporter.write_audience_report(out_dir, audience_result, channel_title))
        except Exception as exc:
            print(f"    [WARNING] audience_report.md: {exc}", file=sys.stderr)

    if brand_result:
        try:
            written.append(md_reporter.write_brand_report(out_dir, brand_result, channel_title))
        except Exception as exc:
            print(f"    [WARNING] brand_report.md: {exc}", file=sys.stderr)

    if knowledge_agg:
        try:
            written.append(md_reporter.write_knowledge_index(out_dir, knowledge_agg, channel_title))
        except Exception as exc:
            print(f"    [WARNING] knowledge_index.md: {exc}", file=sys.stderr)

    try:
        written.append(json_reporter.write_summary(
            out_dir=out_dir,
            channel_id=args.channel_id,
            channel_title=channel_title,
            videos=videos,
            audience=audience_result,
            brand=brand_result,
            location_agg=location_agg or None,
            knowledge_agg=knowledge_agg or None,
        ))
    except Exception as exc:
        print(f"    [WARNING] summary.json: {exc}", file=sys.stderr)

    if all_comments:
        try:
            written.append(csv_reporter.write_comments(out_dir, all_comments, videos))
        except Exception as exc:
            print(f"    [WARNING] comments.csv: {exc}", file=sys.stderr)

    if transcripts:
        try:
            written.append(csv_reporter.write_transcripts(out_dir, transcripts, videos))
        except Exception as exc:
            print(f"    [WARNING] transcripts.csv: {exc}", file=sys.stderr)

    if location_agg:
        try:
            written.extend(csv_reporter.write_all_location_csvs(out_dir, location_agg))
        except Exception as exc:
            print(f"    [WARNING] locations CSV: {exc}", file=sys.stderr)

    if knowledge_agg:
        try:
            written.append(csv_reporter.write_knowledge(out_dir, knowledge_agg))
        except Exception as exc:
            print(f"    [WARNING] knowledge_index.csv: {exc}", file=sys.stderr)

    print(f"\n{'='*60}")
    print(f"Done! {len(written)} files written:")
    for p in written:
        print(f"   {p}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
