#!/usr/bin/env python3
"""
YouTube Channel Analysis Tool
Usage: python main.py --channel @ChannelHandle --max-videos 20
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyse a YouTube channel's audience profile and brand positioning",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --channel @SomeGolfChannel --max-videos 30
  python main.py --channel UCxxxxxxxxxx --max-videos 50 --force-refresh
  python main.py --channel @SomeChannel --skip-comments   # brand analysis only
        """,
    )

    parser.add_argument(
        "--channel",
        required=True,
        help="YouTube channel @handle or Channel ID",
    )
    parser.add_argument(
        "--max-videos",
        type=int,
        default=20,
        metavar="N",
        help="Maximum number of videos to analyse (default: 20)",
    )
    parser.add_argument(
        "--max-comments",
        type=int,
        default=500,
        metavar="N",
        help="Maximum comments to fetch per video (default: 500)",
    )
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Ignore cache and re-fetch all data",
    )
    parser.add_argument(
        "--skip-transcripts",
        action="store_true",
        help="Skip transcript fetching and related analyses (brand, location, knowledge)",
    )
    parser.add_argument(
        "--skip-comments",
        action="store_true",
        help="Skip comment fetching and audience analysis",
    )
    parser.add_argument(
        "--skip-extraction",
        action="store_true",
        help="Skip location/knowledge structured extraction (run audience/brand only)",
    )
    parser.add_argument(
        "--refresh-comments",
        action="store_true",
        help="Re-fetch comments for cached videos (updates top-comment ranking)",
    )
    parser.add_argument(
        "--output-dir",
        default="./reports",
        metavar="DIR",
        help="Report output root directory (default: ./reports)",
    )
    parser.add_argument(
        "--llm",
        choices=["claude", "local"],
        default="claude",
        help="LLM backend to use for analysis (default: claude)",
    )
    parser.add_argument(
        "--llm-model",
        default=None,
        metavar="MODEL",
        help="Override the LLM model name (e.g. qwen2.5:latest for local, claude-haiku-4-5-20251001 for claude)",
    )

    return parser.parse_args()


def _warn(msg: str) -> None:
    print(f"\n[WARNING] {msg}", file=sys.stderr)


def _step(n: int, total: int, msg: str) -> None:
    print(f"\n[{n}/{total}] {msg}")


def main() -> None:
    args = parse_args()

    # ------------------------------------------------------------------ #
    # Bootstrap                                                            #
    # ------------------------------------------------------------------ #
    from config.settings import load_settings
    settings = load_settings()

    from storage.file_store import FileStore
    from storage.cache_manager import CacheManager
    from collectors.youtube_api import YouTubeAPIClient
    from collectors.transcript_fetcher import TranscriptFetcher
    from collectors.comment_scraper import CommentScraper
    from analyzers.audience_analyzer import AudienceAnalyzer
    from analyzers.brand_analyzer import BrandAnalyzer
    from extractors.location_extractor import LocationExtractor
    from extractors.knowledge_extractor import KnowledgeExtractor
    from reporters.markdown_reporter import MarkdownReporter
    from reporters.json_reporter import JSONReporter
    from reporters.csv_reporter import CSVReporter

    # ------------------------------------------------------------------ #
    # LLM client selection                                                 #
    # ------------------------------------------------------------------ #
    if args.llm == "local":
        from analyzers.local_llm_client import LocalLLMClient
        model = args.llm_model or settings.local_llm_model
        llm = LocalLLMClient(model=model, base_url=settings.local_llm_url)
        print(f"[LLM] local Ollama  model={model}  url={settings.local_llm_url}")
    else:
        if not settings.anthropic_api_key:
            print("ANTHROPIC_API_KEY is not set. Use --llm local for local LLM.", file=sys.stderr)
            sys.exit(1)
        from analyzers.claude_client import ClaudeClient
        model = args.llm_model or settings.claude_model
        llm = ClaudeClient(api_key=settings.anthropic_api_key, model=model)
        print(f"[LLM] Claude API  model={model}")

    store = FileStore(base_dir=settings.data_dir)
    cache = CacheManager(store)
    yt = YouTubeAPIClient(api_key=settings.youtube_api_key)
    transcript_fetcher = TranscriptFetcher(
        languages=settings.transcript_languages,
        store=store,
    )
    comment_scraper = CommentScraper(
        api_client=yt,
        store=store,
        max_per_video=args.max_comments,
    )
    audience_analyzer = AudienceAnalyzer(client=llm)
    brand_analyzer = BrandAnalyzer(client=llm)
    location_extractor = LocationExtractor(client=llm)
    knowledge_extractor = KnowledgeExtractor(client=llm)

    md_reporter = MarkdownReporter()
    json_reporter = JSONReporter(store=store)
    csv_reporter = CSVReporter(store=store)

    TOTAL_STEPS = 9

    # ------------------------------------------------------------------ #
    # Step 1 — Resolve channel                                             #
    # ------------------------------------------------------------------ #
    _step(1, TOTAL_STEPS, f"Resolving channel: {args.channel}")
    try:
        channel_id, channel_title = yt.get_channel_id_by_handle(args.channel)
        print(f"   -> {channel_title} ({channel_id})")
    except Exception as exc:
        print(f"Failed to resolve channel: {exc}", file=sys.stderr)
        sys.exit(1)

    out_dir = Path(args.output_dir) / channel_id
    out_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    # Step 2 — Fetch video list & detect new videos                        #
    # ------------------------------------------------------------------ #
    _step(2, TOTAL_STEPS, "Fetching video list, comparing against cache...")
    try:
        videos = yt.list_channel_videos(
            channel_id=channel_id,
            max_results=args.max_videos,
        )
        print(f"   -> {len(videos)} videos fetched")
    except Exception as exc:
        print(f"Failed to fetch video list: {exc}", file=sys.stderr)
        sys.exit(1)

    # Save video list to disk for later reference
    store.save_json(store.video_list_path(channel_id), videos)

    shorts_count = sum(1 for v in videos if v.get("is_short"))
    print(f"   -> Regular: {len(videos) - shorts_count} / Shorts: {shorts_count}")

    # Regular videos first, then Shorts (for comment fetch priority)
    all_video_ids = (
        [v["video_id"] for v in videos if not v.get("is_short")]
        + [v["video_id"] for v in videos if v.get("is_short")]
    )

    if args.force_refresh:
        new_video_ids = all_video_ids
        print("   -> --force-refresh: re-fetching all videos")
    else:
        new_video_ids = cache.get_new_video_ids(channel_id, all_video_ids)
        print(f"   -> New: {len(new_video_ids)} / Cached: {len(all_video_ids) - len(new_video_ids)}")

    # ------------------------------------------------------------------ #
    # Step 3 — Transcripts                                                 #
    # ------------------------------------------------------------------ #
    transcripts: dict = {}
    if not args.skip_transcripts:
        _step(3, TOTAL_STEPS, "Fetching transcripts (new videos only)...")
        try:
            transcripts = transcript_fetcher.fetch_batch(
                video_ids=all_video_ids,
                new_only_ids=new_video_ids,
                channel_id=channel_id,
                force=args.force_refresh,
            )
            fetched = sum(1 for t in transcripts.values() if t)
            print(f"   -> Transcripts fetched: {fetched} / {len(all_video_ids)}")

            # Mark videos that have transcripts
            transcript_set = {vid for vid, t in transcripts.items() if t}
            for v in videos:
                v["has_transcript"] = v["video_id"] in transcript_set
        except Exception as exc:
            _warn(f"Transcript fetch failed, skipping: {exc}")
    else:
        _step(3, TOTAL_STEPS, "Skipping transcripts (--skip-transcripts)")

    # ------------------------------------------------------------------ #
    # Step 4 — Comments                                                    #
    # ------------------------------------------------------------------ #
    all_comments: dict = {}
    if not args.skip_comments:
        _step(4, TOTAL_STEPS, "Fetching comments for regular videos only...")
        try:
            regular_video_ids = [v["video_id"] for v in videos if not v.get("is_short")]
            regular_new_ids = [vid for vid in new_video_ids if vid in set(regular_video_ids)]
            refresh_ids = regular_video_ids if args.refresh_comments else regular_new_ids
            all_comments = comment_scraper.fetch_batch(
                video_ids=regular_video_ids,
                fetch_ids=refresh_ids,
                channel_id=channel_id,
                force=args.force_refresh,
            )
            total_comments = sum(len(c) for c in all_comments.values())
            print(f"   -> {total_comments} comments across {len(all_comments)} videos")
        except Exception as exc:
            _warn(f"Comment fetch failed, skipping: {exc}")
    else:
        _step(4, TOTAL_STEPS, "Skipping comments (--skip-comments)")

    # ------------------------------------------------------------------ #
    # Step 5 — Audience analysis                                           #
    # ------------------------------------------------------------------ #
    audience_result: dict = {}
    if not args.skip_comments and all_comments:
        _step(5, TOTAL_STEPS, "Claude: analysing audience profile...")
        try:
            audience_result = audience_analyzer.analyze(
                all_comments=all_comments,
                videos=videos,
                channel_title=channel_title,
            )
            print(f"   -> Done ({audience_result.get('comment_count', 0)} comments)")
        except Exception as exc:
            _warn(f"Audience analysis failed: {exc}")
    else:
        _step(5, TOTAL_STEPS, "Skipping audience analysis (no comment data)")

    # ------------------------------------------------------------------ #
    # Step 6 — Brand analysis                                              #
    # ------------------------------------------------------------------ #
    brand_result: dict = {}
    if not args.skip_transcripts and transcripts:
        _step(6, TOTAL_STEPS, "Claude: analysing brand positioning...")
        try:
            brand_result = brand_analyzer.analyze(
                transcripts=transcripts,
                videos=videos,
                channel_title=channel_title,
            )
            print(f"   -> Done ({brand_result.get('video_count', 0)} videos)")
        except Exception as exc:
            _warn(f"Brand analysis failed: {exc}")
    else:
        _step(6, TOTAL_STEPS, "Skipping brand analysis (no transcript data)")

    # ------------------------------------------------------------------ #
    # Step 7 — Location / food / equipment extraction                      #
    # ------------------------------------------------------------------ #
    location_agg: dict = {}
    if not args.skip_transcripts and not args.skip_extraction and transcripts:
        _step(7, TOTAL_STEPS, "Extracting locations, food, equipment...")
        try:
            loc_results = location_extractor.extract_batch(
                videos=videos,
                transcripts=transcripts,
            )
            location_agg = location_extractor.aggregate(loc_results)
            # Save raw per-video JSON
            store.save_json(
                str(out_dir / "locations_database.json"),
                location_agg,
            )
            stats = location_agg.get("stats", {})
            print(
                f"   -> Locations: {stats.get('total_locations', 0)}  "
                f"Food: {stats.get('total_food_items', 0)}  "
                f"Equipment: {stats.get('total_equipment_items', 0)}"
            )
        except Exception as exc:
            _warn(f"Location/food/equipment extraction failed: {exc}")
    else:
        _step(7, TOTAL_STEPS, "Skipping location extraction")

    # ------------------------------------------------------------------ #
    # Step 8 — Knowledge extraction                                        #
    # ------------------------------------------------------------------ #
    knowledge_agg: dict = {}
    if not args.skip_transcripts and not args.skip_extraction and transcripts:
        _step(8, TOTAL_STEPS, "Extracting golf knowledge index...")
        try:
            know_results = knowledge_extractor.extract_batch(
                videos=videos,
                transcripts=transcripts,
            )
            knowledge_agg = knowledge_extractor.aggregate(know_results)
            # Save raw per-video JSON
            store.save_json(
                str(out_dir / "knowledge_index.json"),
                knowledge_agg,
            )
            stats = knowledge_agg.get("stats", {})
            print(
                f"   -> {stats.get('total_knowledge_items', 0)} knowledge items "
                f"across {stats.get('videos_with_knowledge', 0)} videos"
            )
        except Exception as exc:
            _warn(f"Knowledge index extraction failed: {exc}")
    else:
        _step(8, TOTAL_STEPS, "Skipping knowledge index extraction")

    # ------------------------------------------------------------------ #
    # Step 9 — Output reports                                              #
    # ------------------------------------------------------------------ #
    _step(9, TOTAL_STEPS, f"Writing reports -> {out_dir}")
    written: list[Path] = []

    try:
        if audience_result:
            p = md_reporter.write_audience_report(out_dir, audience_result, channel_title)
            written.append(p)
    except Exception as exc:
        _warn(f"audience_report.md write failed: {exc}")

    try:
        if brand_result:
            p = md_reporter.write_brand_report(out_dir, brand_result, channel_title)
            written.append(p)
    except Exception as exc:
        _warn(f"brand_report.md write failed: {exc}")

    try:
        if knowledge_agg:
            p = md_reporter.write_knowledge_index(out_dir, knowledge_agg, channel_title)
            written.append(p)
    except Exception as exc:
        _warn(f"knowledge_index.md write failed: {exc}")

    try:
        p = json_reporter.write_summary(
            out_dir=out_dir,
            channel_id=channel_id,
            channel_title=channel_title,
            videos=videos,
            audience=audience_result,
            brand=brand_result,
            location_agg=location_agg or None,
            knowledge_agg=knowledge_agg or None,
        )
        written.append(p)
    except Exception as exc:
        _warn(f"summary.json write failed: {exc}")

    try:
        if all_comments:
            p = csv_reporter.write_comments(out_dir, all_comments, videos)
            written.append(p)
    except Exception as exc:
        _warn(f"comments.csv write failed: {exc}")

    try:
        if transcripts:
            p = csv_reporter.write_transcripts(out_dir, transcripts, videos)
            written.append(p)
    except Exception as exc:
        _warn(f"transcripts.csv write failed: {exc}")

    try:
        if location_agg:
            written.extend(csv_reporter.write_all_location_csvs(out_dir, location_agg))
    except Exception as exc:
        _warn(f"locations CSV write failed: {exc}")

    try:
        if knowledge_agg:
            p = csv_reporter.write_knowledge(out_dir, knowledge_agg)
            written.append(p)
    except Exception as exc:
        _warn(f"knowledge_index.csv write failed: {exc}")

    # ------------------------------------------------------------------ #
    # Summary                                                              #
    # ------------------------------------------------------------------ #
    print(f"\n{'='*60}")
    print(f"Done! {len(written)} files written:")
    for p in written:
        print(f"   {p}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
