#!/usr/bin/env python3
"""
YouTube Channel Analysis Tool
用法：python main.py --channel @ChannelHandle --max-videos 20
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="分析 YouTube 頻道的 TA 輪廓和個人品牌定位",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例：
  python main.py --channel @SomeGolfChannel --max-videos 30
  python main.py --channel UCxxxxxxxxxx --max-videos 50 --force-refresh
  python main.py --channel @SomeChannel --skip-comments   # 只分析品牌定位
        """,
    )

    parser.add_argument(
        "--channel",
        required=True,
        help="YouTube 頻道 @handle 或 Channel ID",
    )
    parser.add_argument(
        "--max-videos",
        type=int,
        default=20,
        metavar="N",
        help="最多分析幾支影片（預設 20）",
    )
    parser.add_argument(
        "--max-comments",
        type=int,
        default=100,
        metavar="N",
        help="每支影片最多抓幾則留言（預設 100）",
    )
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="忽略快取，重新抓取所有資料",
    )
    parser.add_argument(
        "--skip-transcripts",
        action="store_true",
        help="跳過逐字稿抓取及相關分析（品牌定位、地點萃取、知識索引）",
    )
    parser.add_argument(
        "--skip-comments",
        action="store_true",
        help="跳過留言抓取及 TA 分析",
    )
    parser.add_argument(
        "--skip-extraction",
        action="store_true",
        help="跳過 location/knowledge 結構化萃取（僅執行 audience/brand 分析）",
    )
    parser.add_argument(
        "--refresh-comments",
        action="store_true",
        help="重新抓取已快取影片的留言（更新熱門留言排序）",
    )
    parser.add_argument(
        "--output-dir",
        default="./reports",
        metavar="DIR",
        help="報告輸出根目錄（預設 ./reports）",
    )

    return parser.parse_args()


def _warn(msg: str) -> None:
    print(f"\n⚠️  {msg}", file=sys.stderr)


def _step(n: int, total: int, msg: str) -> None:
    print(f"\n[{n}/{total}] {msg}")


def main() -> None:
    args = parse_args()

    # ------------------------------------------------------------------ #
    # Bootstrap                                                            #
    # ------------------------------------------------------------------ #
    from config.settings import load_settings
    settings = load_settings()

    # Validate required API keys early
    missing = []
    if not settings.youtube_api_key:
        missing.append("YOUTUBE_API_KEY")
    if not settings.anthropic_api_key:
        missing.append("ANTHROPIC_API_KEY")
    if missing:
        print(
            f"❌ 缺少必要的環境變數：{', '.join(missing)}\n"
            "   請複製 .env.example → .env 並填入 API keys。",
            file=sys.stderr,
        )
        sys.exit(1)

    from storage.file_store import FileStore
    from storage.cache_manager import CacheManager
    from collectors.youtube_api import YouTubeAPIClient
    from collectors.transcript_fetcher import TranscriptFetcher
    from collectors.comment_scraper import CommentScraper
    from analyzers.claude_client import ClaudeClient
    from analyzers.audience_analyzer import AudienceAnalyzer
    from analyzers.brand_analyzer import BrandAnalyzer
    from extractors.location_extractor import LocationExtractor
    from extractors.knowledge_extractor import KnowledgeExtractor
    from reporters.markdown_reporter import MarkdownReporter
    from reporters.json_reporter import JSONReporter
    from reporters.csv_reporter import CSVReporter

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
    claude = ClaudeClient(
        api_key=settings.anthropic_api_key,
        model=settings.claude_model,
        max_tokens=settings.claude_max_tokens,
    )
    audience_analyzer = AudienceAnalyzer(client=claude)
    brand_analyzer = BrandAnalyzer(client=claude)
    location_extractor = LocationExtractor(client=claude)
    knowledge_extractor = KnowledgeExtractor(client=claude)

    md_reporter = MarkdownReporter()
    json_reporter = JSONReporter(store=store)
    csv_reporter = CSVReporter(store=store)

    TOTAL_STEPS = 9

    # ------------------------------------------------------------------ #
    # Step 1 — Resolve channel                                             #
    # ------------------------------------------------------------------ #
    _step(1, TOTAL_STEPS, f"解析頻道：{args.channel}")
    try:
        channel_id, channel_title = yt.get_channel_id_by_handle(args.channel)
        print(f"   → {channel_title} ({channel_id})")
    except Exception as exc:
        print(f"❌ 無法解析頻道：{exc}", file=sys.stderr)
        sys.exit(1)

    out_dir = Path(args.output_dir) / channel_id
    out_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    # Step 2 — Fetch video list & detect new videos                        #
    # ------------------------------------------------------------------ #
    _step(2, TOTAL_STEPS, "取影片列表，對比快取找出新影片…")
    try:
        videos = yt.list_channel_videos(
            channel_id=channel_id,
            max_results=args.max_videos,
        )
        print(f"   → 取得 {len(videos)} 支影片")
    except Exception as exc:
        print(f"❌ 取影片列表失敗：{exc}", file=sys.stderr)
        sys.exit(1)

    all_video_ids = [v["video_id"] for v in videos]

    if args.force_refresh:
        new_video_ids = all_video_ids
        print("   → --force-refresh：全部重新抓取")
    else:
        new_video_ids = cache.get_new_video_ids(channel_id, all_video_ids)
        print(f"   → 新影片：{len(new_video_ids)} 支 ／ 快取：{len(all_video_ids) - len(new_video_ids)} 支")

    # ------------------------------------------------------------------ #
    # Step 3 — Transcripts                                                 #
    # ------------------------------------------------------------------ #
    transcripts: dict = {}
    if not args.skip_transcripts:
        _step(3, TOTAL_STEPS, "抓取逐字稿（僅新影片）…")
        try:
            transcripts = transcript_fetcher.fetch_batch(
                video_ids=all_video_ids,
                new_only_ids=new_video_ids,
                channel_id=channel_id,
                force=args.force_refresh,
            )
            fetched = sum(1 for t in transcripts.values() if t)
            print(f"   → 成功取得逐字稿：{fetched} / {len(all_video_ids)} 支")

            # Mark videos that have transcripts
            transcript_set = {vid for vid, t in transcripts.items() if t}
            for v in videos:
                v["has_transcript"] = v["video_id"] in transcript_set
        except Exception as exc:
            _warn(f"逐字稿抓取失敗，跳過：{exc}")
    else:
        _step(3, TOTAL_STEPS, "跳過逐字稿（--skip-transcripts）")

    # ------------------------------------------------------------------ #
    # Step 4 — Comments                                                    #
    # ------------------------------------------------------------------ #
    all_comments: dict = {}
    if not args.skip_comments:
        _step(4, TOTAL_STEPS, "抓取留言（僅新影片）…")
        try:
            refresh_ids = all_video_ids if args.refresh_comments else new_video_ids
            all_comments = comment_scraper.fetch_batch(
                video_ids=all_video_ids,
                fetch_ids=refresh_ids,
                channel_id=channel_id,
                force=args.force_refresh,
            )
            total_comments = sum(len(c) for c in all_comments.values())
            print(f"   → 共 {total_comments} 則留言（{len(all_comments)} 支影片）")
        except Exception as exc:
            _warn(f"留言抓取失敗，跳過：{exc}")
    else:
        _step(4, TOTAL_STEPS, "跳過留言（--skip-comments）")

    # ------------------------------------------------------------------ #
    # Step 5 — Audience analysis                                           #
    # ------------------------------------------------------------------ #
    audience_result: dict = {}
    if not args.skip_comments and all_comments:
        _step(5, TOTAL_STEPS, "Claude 分析 TA 輪廓…")
        try:
            audience_result = audience_analyzer.analyze(
                all_comments=all_comments,
                videos=videos,
                channel_title=channel_title,
            )
            print(f"   → 分析完成（{audience_result.get('comment_count', 0)} 則留言）")
        except Exception as exc:
            _warn(f"TA 分析失敗：{exc}")
    else:
        _step(5, TOTAL_STEPS, "跳過 TA 分析（無留言資料）")

    # ------------------------------------------------------------------ #
    # Step 6 — Brand analysis                                              #
    # ------------------------------------------------------------------ #
    brand_result: dict = {}
    if not args.skip_transcripts and transcripts:
        _step(6, TOTAL_STEPS, "Claude 分析品牌定位…")
        try:
            brand_result = brand_analyzer.analyze(
                transcripts=transcripts,
                videos=videos,
                channel_title=channel_title,
            )
            print(f"   → 分析完成（{brand_result.get('video_count', 0)} 支影片）")
        except Exception as exc:
            _warn(f"品牌分析失敗：{exc}")
    else:
        _step(6, TOTAL_STEPS, "跳過品牌分析（無逐字稿資料）")

    # ------------------------------------------------------------------ #
    # Step 7 — Location / food / equipment extraction                      #
    # ------------------------------------------------------------------ #
    location_agg: dict = {}
    if not args.skip_transcripts and not args.skip_extraction and transcripts:
        _step(7, TOTAL_STEPS, "萃取地點、食物、設備資料庫…")
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
                f"   → 地點 {stats.get('total_locations', 0)} 筆 ／ "
                f"食物 {stats.get('total_food_items', 0)} 筆 ／ "
                f"設備 {stats.get('total_equipment_items', 0)} 筆"
            )
        except Exception as exc:
            _warn(f"地點/食物/設備萃取失敗：{exc}")
    else:
        _step(7, TOTAL_STEPS, "跳過地點萃取")

    # ------------------------------------------------------------------ #
    # Step 8 — Knowledge extraction                                        #
    # ------------------------------------------------------------------ #
    knowledge_agg: dict = {}
    if not args.skip_transcripts and not args.skip_extraction and transcripts:
        _step(8, TOTAL_STEPS, "萃取高爾夫知識索引…")
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
                f"   → 知識點 {stats.get('total_knowledge_items', 0)} 個 ／ "
                f"涵蓋 {stats.get('videos_with_knowledge', 0)} 支影片"
            )
        except Exception as exc:
            _warn(f"知識索引萃取失敗：{exc}")
    else:
        _step(8, TOTAL_STEPS, "跳過知識索引萃取")

    # ------------------------------------------------------------------ #
    # Step 9 — Output reports                                              #
    # ------------------------------------------------------------------ #
    _step(9, TOTAL_STEPS, f"輸出報告 → {out_dir}")
    written: list[Path] = []

    try:
        if audience_result:
            p = md_reporter.write_audience_report(out_dir, audience_result, channel_title)
            written.append(p)
    except Exception as exc:
        _warn(f"audience_report.md 寫入失敗：{exc}")

    try:
        if brand_result:
            p = md_reporter.write_brand_report(out_dir, brand_result, channel_title)
            written.append(p)
    except Exception as exc:
        _warn(f"brand_report.md 寫入失敗：{exc}")

    try:
        if knowledge_agg:
            p = md_reporter.write_knowledge_index(out_dir, knowledge_agg, channel_title)
            written.append(p)
    except Exception as exc:
        _warn(f"knowledge_index.md 寫入失敗：{exc}")

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
        _warn(f"summary.json 寫入失敗：{exc}")

    try:
        if all_comments:
            p = csv_reporter.write_comments(out_dir, all_comments, videos)
            written.append(p)
    except Exception as exc:
        _warn(f"comments.csv 寫入失敗：{exc}")

    try:
        if transcripts:
            p = csv_reporter.write_transcripts(out_dir, transcripts, videos)
            written.append(p)
    except Exception as exc:
        _warn(f"transcripts.csv 寫入失敗：{exc}")

    try:
        if location_agg:
            written.extend(csv_reporter.write_all_location_csvs(out_dir, location_agg))
    except Exception as exc:
        _warn(f"locations CSV 寫入失敗：{exc}")

    try:
        if knowledge_agg:
            p = csv_reporter.write_knowledge(out_dir, knowledge_agg)
            written.append(p)
    except Exception as exc:
        _warn(f"knowledge_index.csv 寫入失敗：{exc}")

    # ------------------------------------------------------------------ #
    # Summary                                                              #
    # ------------------------------------------------------------------ #
    print(f"\n{'='*60}")
    print(f"✅ 分析完成！共輸出 {len(written)} 個檔案：")
    for p in written:
        print(f"   {p}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
