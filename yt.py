#!/usr/bin/env python3
"""
YouTube Channel Analysis Tool

Usage:
  python yt.py fetch   --channel @Handle          # download data from YouTube
  python yt.py analyze --channel-id UCxxxx        # analyse cached data (no YouTube API)
  python yt.py run     --channel @Handle          # fetch + analyse in one step
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


# ─────────────────────────────────────────────
# Shared helpers
# ─────────────────────────────────────────────

def _step(msg: str) -> None:
    print(f"\n>>> {msg}")


def _warn(msg: str) -> None:
    print(f"[WARNING] {msg}", file=sys.stderr)


def _build_llm(args, settings=None):
    """Build an LLM client. CLI flags override .env/settings."""
    import os
    from dotenv import load_dotenv
    load_dotenv()

    backend = getattr(args, "llm", None) or (
        settings.llm_backend if settings else os.getenv("LLM_BACKEND", "claude")
    )

    if backend == "local":
        from analyzers.local_llm_client import LocalLLMClient
        model = getattr(args, "model", None) or (
            settings.local_llm_model if settings else os.getenv("LOCAL_LLM_MODEL", "qwen3:8b")
        )
        url = getattr(args, "ollama_url", None) or (
            settings.local_llm_url if settings else os.getenv("LOCAL_LLM_URL", "http://localhost:11434/v1")
        )
        print(f"[LLM] Ollama  model={model}  url={url}")
        return LocalLLMClient(model=model, base_url=url)
    else:
        from analyzers.claude_client import ClaudeClient
        api_key = (settings.anthropic_api_key if settings else None) or os.getenv("ANTHROPIC_API_KEY", "")
        if not api_key:
            print("ANTHROPIC_API_KEY is not set. Use --llm local or set LLM_BACKEND=local.", file=sys.stderr)
            sys.exit(1)
        model = getattr(args, "model", None) or (
            settings.claude_model if settings else os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
        )
        print(f"[LLM] Claude  model={model}")
        return ClaudeClient(api_key=api_key, model=model)


def _do_fetch(channel: str, settings) -> tuple[str, str, list, dict, dict]:
    """Resolve channel, fetch videos/transcripts/comments.
    Returns (channel_id, channel_title, videos, transcripts, comments)."""
    from storage.file_store import FileStore
    from storage.cache_manager import CacheManager
    from collectors.youtube_api import YouTubeAPIClient
    from collectors.transcript_fetcher import TranscriptFetcher
    from collectors.comment_scraper import CommentScraper

    store = FileStore(base_dir=settings.data_dir)
    cache = CacheManager(store)
    yt    = YouTubeAPIClient(api_key=settings.youtube_api_key)
    tf    = TranscriptFetcher(preferred_languages=settings.transcript_languages)
    cs    = CommentScraper(api_client=yt, store=store, max_per_video=settings.max_comments_per_video)

    # Resolve channel
    _step(f"Resolving channel: {channel}")
    try:
        channel_id, channel_title = yt.get_channel_id_by_handle(channel)
        print(f"    {channel_title} ({channel_id})")
    except Exception as exc:
        print(f"Failed to resolve channel: {exc}", file=sys.stderr)
        sys.exit(1)

    # Video list
    _step("Fetching video list...")
    try:
        videos = yt.list_channel_videos(channel_id=channel_id, max_results=settings.max_videos)
        store.save_json(store.video_list_path(channel_id), videos)
    except Exception as exc:
        print(f"Failed to fetch video list: {exc}", file=sys.stderr)
        sys.exit(1)

    shorts_count = sum(1 for v in videos if v.get("is_short"))
    print(f"    {len(videos)} videos  (Regular: {len(videos) - shorts_count} / Shorts: {shorts_count})")

    all_video_ids = (
        [v["video_id"] for v in videos if not v.get("is_short")]
        + [v["video_id"] for v in videos if v.get("is_short")]
    )
    new_video_ids = cache.get_new_video_ids(channel_id, all_video_ids)
    print(f"    New: {len(new_video_ids)} / Cached: {len(all_video_ids) - len(new_video_ids)}")

    # Transcripts
    transcripts: dict = {}
    _step("Fetching transcripts (new videos only)...")
    try:
        transcripts = tf.fetch_batch(
            video_ids=all_video_ids,
            new_only_ids=new_video_ids,
            channel_id=channel_id,
        )
        fetched = sum(1 for t in transcripts.values() if t)
        print(f"    {fetched} / {len(all_video_ids)} transcripts fetched")
        transcript_set = {vid for vid, t in transcripts.items() if t}
        for v in videos:
            v["has_transcript"] = v["video_id"] in transcript_set
    except Exception as exc:
        _warn(f"Transcript fetch failed: {exc}")

    # Comments
    all_comments: dict = {}
    _step("Fetching comments (regular videos only)...")
    try:
        regular_ids = [v["video_id"] for v in videos if not v.get("is_short")]
        new_regular  = [vid for vid in new_video_ids if vid in set(regular_ids)]
        all_comments = cs.fetch_batch(
            video_ids=regular_ids,
            fetch_ids=new_regular,
            channel_id=channel_id,
        )
        total = sum(len(c) for c in all_comments.values())
        print(f"    {total} comments across {len(all_comments)} videos")
    except Exception as exc:
        _warn(f"Comment fetch failed: {exc}")

    return channel_id, channel_title, videos, transcripts, all_comments


def _load_cached_data(data_dir: Path, channel_id: str) -> tuple[list, dict, dict]:
    """Load videos, transcripts, comments from local disk."""
    import json

    videos: list = []
    vpath = data_dir / "raw" / "videos" / channel_id / "video_list.json"
    if vpath.exists():
        with open(vpath, encoding="utf-8") as f:
            videos = json.load(f)

    transcripts: dict = {}
    td = data_dir / "raw" / "transcripts" / channel_id
    if td.exists():
        for p in td.glob("*.json"):
            with open(p, encoding="utf-8") as f:
                transcripts[p.stem] = json.load(f)

    all_comments: dict = {}
    cd = data_dir / "raw" / "comments" / channel_id
    if cd.exists():
        for p in cd.glob("*.json"):
            with open(p, encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    all_comments[p.stem] = data

    return videos, transcripts, all_comments


def _do_analyze(
    args,
    channel_id: str,
    channel_title: str,
    videos: list,
    transcripts: dict,
    all_comments: dict,
    llm,
    data_dir: Path,
    out_dir: Path,
) -> None:
    """Run LLM analysis, extraction, and write reports."""
    from analyzers.audience_analyzer import AudienceAnalyzer
    from analyzers.brand_analyzer import BrandAnalyzer
    from extractors.location_extractor import LocationExtractor
    from extractors.knowledge_extractor import KnowledgeExtractor
    from reporters.markdown_reporter import MarkdownReporter
    from reporters.json_reporter import JSONReporter
    from reporters.csv_reporter import CSVReporter
    from storage.file_store import FileStore

    store = FileStore(base_dir=str(data_dir))
    md = MarkdownReporter()
    jr = JSONReporter(store=store)
    cr = CSVReporter(store=store)
    written: list[Path] = []

    # Optional video limit
    max_videos = getattr(args, "max_videos", None)
    if max_videos:
        videos = videos[:max_videos]
        allowed = {v["video_id"] for v in videos}
        transcripts  = {k: v for k, v in transcripts.items()  if k in allowed}
        all_comments = {k: v for k, v in all_comments.items() if k in allowed}

    # Audience analysis
    audience_result: dict = {}
    if not getattr(args, "skip_audience", False) and all_comments:
        _step("Audience analysis...")
        try:
            audience_result = AudienceAnalyzer(client=llm).analyze(
                all_comments=all_comments, videos=videos, channel_title=channel_title,
            )
            print(f"    {audience_result.get('comment_count', 0)} comments analysed")
        except Exception as exc:
            _warn(f"Audience analysis failed: {exc}")
    else:
        _step("Skipping audience analysis")

    # Brand analysis
    brand_result: dict = {}
    if not getattr(args, "skip_brand", False) and transcripts:
        _step("Brand analysis...")
        try:
            brand_result = BrandAnalyzer(client=llm).analyze(
                transcripts=transcripts, videos=videos, channel_title=channel_title,
            )
            print(f"    {brand_result.get('video_count', 0)} videos analysed")
        except Exception as exc:
            _warn(f"Brand analysis failed: {exc}")
    else:
        _step("Skipping brand analysis")

    # Location / knowledge extraction
    location_agg: dict = {}
    knowledge_agg: dict = {}
    if not getattr(args, "skip_extraction", False) and transcripts:
        _step("Extracting locations, food, equipment...")
        try:
            le = LocationExtractor(client=llm)
            location_agg = le.aggregate(le.extract_batch(videos=videos, transcripts=transcripts))
            store.save_json(str(out_dir / "locations_database.json"), location_agg)
            s = location_agg.get("stats", {})
            print(f"    Locations: {s.get('total_locations', 0)}  "
                  f"Food: {s.get('total_food_items', 0)}  "
                  f"Equipment: {s.get('total_equipment_items', 0)}")
        except Exception as exc:
            _warn(f"Location extraction failed: {exc}")

        _step("Extracting knowledge index...")
        try:
            ke = KnowledgeExtractor(client=llm)
            knowledge_agg = ke.aggregate(ke.extract_batch(videos=videos, transcripts=transcripts))
            store.save_json(str(out_dir / "knowledge_index.json"), knowledge_agg)
            s = knowledge_agg.get("stats", {})
            print(f"    {s.get('total_knowledge_items', 0)} items "
                  f"across {s.get('videos_with_knowledge', 0)} videos")
        except Exception as exc:
            _warn(f"Knowledge extraction failed: {exc}")
    else:
        _step("Skipping extraction")

    # Write reports
    _step(f"Writing reports → {out_dir}")

    if audience_result:
        try: written.append(md.write_audience_report(out_dir, audience_result, channel_title))
        except Exception as exc: _warn(f"audience_report.md: {exc}")

    if brand_result:
        try: written.append(md.write_brand_report(out_dir, brand_result, channel_title))
        except Exception as exc: _warn(f"brand_report.md: {exc}")

    if knowledge_agg:
        try: written.append(md.write_knowledge_index(out_dir, knowledge_agg, channel_title))
        except Exception as exc: _warn(f"knowledge_index.md: {exc}")

    try:
        written.append(jr.write_summary(
            out_dir=out_dir, channel_id=channel_id, channel_title=channel_title,
            videos=videos, audience=audience_result, brand=brand_result,
            location_agg=location_agg or None, knowledge_agg=knowledge_agg or None,
        ))
    except Exception as exc: _warn(f"summary.json: {exc}")

    if all_comments:
        try: written.append(cr.write_comments(out_dir, all_comments, videos))
        except Exception as exc: _warn(f"comments.csv: {exc}")

    if transcripts:
        try: written.append(cr.write_transcripts(out_dir, transcripts, videos))
        except Exception as exc: _warn(f"transcripts.csv: {exc}")

    if location_agg:
        try: written.extend(cr.write_all_location_csvs(out_dir, location_agg))
        except Exception as exc: _warn(f"locations CSV: {exc}")

    if knowledge_agg:
        try: written.append(cr.write_knowledge(out_dir, knowledge_agg))
        except Exception as exc: _warn(f"knowledge_index.csv: {exc}")

    print(f"\n{'='*60}")
    print(f"Done! {len(written)} files written:")
    for p in written:
        print(f"   {p}")
    print(f"{'='*60}\n")


# ─────────────────────────────────────────────
# Subcommand handlers
# ─────────────────────────────────────────────

def cmd_fetch(args) -> None:
    from config.settings import load_settings
    settings = load_settings()
    if args.max_videos:
        settings.max_videos = args.max_videos
    channel_id, _, _, _, _ = _do_fetch(args.channel, settings)
    print(f"\nData saved to {settings.data_dir}/")
    print(f"To analyse: python yt.py analyze --channel-id {channel_id}")


def cmd_analyze(args) -> None:
    import os
    from dotenv import load_dotenv
    load_dotenv()

    data_dir = Path(getattr(args, "data_dir", None) or os.getenv("DATA_DIR", "./data"))
    out_root = Path(getattr(args, "output_dir", None) or os.getenv("REPORTS_DIR", "./reports"))
    out_dir  = out_root / args.channel_id
    out_dir.mkdir(parents=True, exist_ok=True)

    _step("Loading cached data...")
    videos, transcripts, all_comments = _load_cached_data(data_dir, args.channel_id)
    if not videos and not transcripts:
        print(f"No cached data found for {args.channel_id} in {data_dir}", file=sys.stderr)
        sys.exit(1)

    channel_title = videos[0].get("channel_title", args.channel_id) if videos else args.channel_id
    total_comments = sum(len(c) for c in all_comments.values())
    print(f"    {len(videos)} videos, {len(transcripts)} transcripts, {total_comments} comments")

    if not videos:
        video_ids = set(transcripts) | set(all_comments)
        videos = [{"video_id": vid, "title": vid, "view_count": 0, "is_short": False} for vid in video_ids]

    llm = _build_llm(args)
    _do_analyze(args, args.channel_id, channel_title, videos, transcripts, all_comments, llm, data_dir, out_dir)


def cmd_run(args) -> None:
    from config.settings import load_settings
    settings = load_settings()
    if args.max_videos:
        settings.max_videos = args.max_videos

    channel_id, channel_title, videos, transcripts, all_comments = _do_fetch(args.channel, settings)

    data_dir = Path(settings.data_dir)
    out_dir  = Path(settings.reports_dir) / channel_id
    out_dir.mkdir(parents=True, exist_ok=True)

    llm = _build_llm(args, settings)
    _do_analyze(args, channel_id, channel_title, videos, transcripts, all_comments, llm, data_dir, out_dir)


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

def _add_llm_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--llm", choices=["claude", "local"],
                   help="LLM backend (overrides .env LLM_BACKEND)")
    p.add_argument("--model",
                   help="Model name (overrides .env CLAUDE_MODEL / LOCAL_LLM_MODEL)")
    p.add_argument("--ollama-url", dest="ollama_url", default=None,
                   help="Ollama base URL (overrides .env LOCAL_LLM_URL)")


def _add_analysis_args(p: argparse.ArgumentParser) -> None:
    _add_llm_args(p)
    p.add_argument("--skip-audience",   action="store_true", help="Skip audience analysis")
    p.add_argument("--skip-brand",      action="store_true", help="Skip brand analysis")
    p.add_argument("--skip-extraction", action="store_true", help="Skip location/knowledge extraction")
    p.add_argument("--max-videos", type=int, default=None,   help="Limit number of videos analysed")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="yt",
        description="YouTube Channel Analysis Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
commands:
  fetch    Download videos, transcripts, and comments from YouTube
  analyze  Run LLM analysis on already-downloaded data (no YouTube API needed)
  run      Fetch + analyse in one step

examples:
  python yt.py fetch   --channel @SomeChannel
  python yt.py analyze --channel-id UCxxxxxxxxxx --llm local --skip-extraction
  python yt.py run     --channel @SomeChannel --llm local
        """,
    )
    sub = parser.add_subparsers(dest="command", metavar="command")
    sub.required = True

    # fetch
    p_fetch = sub.add_parser("fetch", help="Download data from YouTube")
    p_fetch.add_argument("--channel", required=True, help="Channel @handle or ID")
    p_fetch.add_argument("--max-videos", type=int, default=None, help="Limit number of videos to fetch (overrides .env MAX_VIDEOS)")
    p_fetch.set_defaults(func=cmd_fetch)

    # analyze
    p_analyze = sub.add_parser("analyze", help="Analyse cached data (no YouTube API needed)")
    p_analyze.add_argument("--channel-id", required=True, dest="channel_id",
                           help="Channel ID (from the data/ directory)")
    p_analyze.add_argument("--data-dir",   default=None, dest="data_dir",
                           help="Data directory (default: DATA_DIR from .env or ./data)")
    p_analyze.add_argument("--output-dir", default=None, dest="output_dir",
                           help="Report output directory (default: REPORTS_DIR from .env or ./reports)")
    _add_analysis_args(p_analyze)
    p_analyze.set_defaults(func=cmd_analyze)

    # run
    p_run = sub.add_parser("run", help="Fetch data then analyse (requires YouTube API)")
    p_run.add_argument("--channel", required=True, help="Channel @handle or ID")
    _add_analysis_args(p_run)
    p_run.set_defaults(func=cmd_run)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
