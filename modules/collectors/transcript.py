import json
import re

import requests
import yt_dlp
from tqdm import tqdm


class TranscriptFetcher:
    def __init__(self, preferred_languages: list | None = None, store=None):
        self.preferred_languages = preferred_languages or ["ja", "zh-Hant", "zh-Hans", "en"]
        self.store = store

    def fetch(self, video_id: str) -> dict | None:
        """Fetch transcript for a single video. Returns dict or None."""
        result = self._fetch_ytdlp(video_id)
        if result is not None:
            return result
        return self._fetch_fallback(video_id)

    def fetch_batch(
        self,
        video_ids: list,
        new_only_ids: list | None = None,
        channel_id: str | None = None,
        force: bool = False,
    ) -> dict:
        """
        Fetch transcripts for multiple videos, using cache for non-new videos.
        Returns {video_id: transcript_dict_or_None} for all video_ids.
        """
        fetch_set = set(new_only_ids if new_only_ids is not None else video_ids)
        results = {}

        to_fetch = []
        for video_id in video_ids:
            if not force and video_id not in fetch_set:
                if self.store and channel_id:
                    path = self.store.transcript_path(channel_id, video_id)
                    cached = self.store.load_json(path)
                    if cached is not None:
                        results[video_id] = cached
                        continue
            to_fetch.append(video_id)

        for video_id in tqdm(to_fetch, desc="Fetching transcripts", unit="vid"):
            transcript = self.fetch(video_id)
            results[video_id] = transcript
            if transcript and self.store and channel_id:
                path = self.store.transcript_path(channel_id, video_id)
                self.store.save_json(path, transcript)

        return results

    def _fetch_ytdlp(self, video_id: str) -> dict | None:
        url = f"https://www.youtube.com/watch?v={video_id}"
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "ignoreerrors": True,
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
            if not info:
                return None
        except Exception:
            return None

        for is_auto in [False, True]:
            key = "automatic_captions" if is_auto else "subtitles"
            subs_dict = info.get(key, {}) or {}

            for lang in self.preferred_languages:
                if lang not in subs_dict:
                    continue

                sub_url, sub_fmt = self._pick_sub_format(subs_dict[lang])
                if not sub_url:
                    continue

                try:
                    resp = requests.get(sub_url, timeout=15)
                    resp.raise_for_status()
                except Exception:
                    continue

                segments = (
                    self._parse_json3(resp.text)
                    if sub_fmt == "json3"
                    else self._parse_vtt(resp.text)
                )
                if not segments:
                    continue

                full_text = " ".join(
                    s["text"].replace("\n", " ").strip()
                    for s in segments
                    if s["text"].strip()
                )
                return {
                    "video_id": video_id,
                    "language": lang,
                    "is_generated": is_auto,
                    "full_text": full_text,
                    "segments": segments,
                }

        return None

    def _pick_sub_format(self, formats: list) -> tuple[str | None, str | None]:
        for preferred_ext in ("json3", "vtt"):
            for fmt in formats:
                if fmt.get("ext") == preferred_ext:
                    return fmt["url"], preferred_ext
        if formats:
            fmt = formats[0]
            return fmt.get("url"), fmt.get("ext")
        return None, None

    def _parse_json3(self, text: str) -> list:
        try:
            data = json.loads(text)
        except Exception:
            return []
        segments = []
        for event in data.get("events", []):
            if "segs" not in event:
                continue
            seg_text = "".join(s.get("utf8", "") for s in event["segs"]).strip()
            if not seg_text or seg_text == "\n":
                continue
            segments.append({
                "text": seg_text,
                "start": event.get("tStartMs", 0) / 1000,
                "duration": event.get("dDurationMs", 0) / 1000,
            })
        return segments

    def _parse_vtt(self, text: str) -> list:
        segments = []
        for block in re.split(r"\n\n+", text):
            lines = block.strip().split("\n")
            ts_idx = next((i for i, l in enumerate(lines) if "-->" in l), None)
            if ts_idx is None:
                continue
            ts_line = lines[ts_idx]
            text_lines = lines[ts_idx + 1:]
            if not text_lines:
                continue

            m = re.match(
                r"(\d+):(\d+):(\d+[.,]\d+)\s*-->\s*(\d+):(\d+):(\d+[.,]\d+)", ts_line
            )
            if m:
                start = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3).replace(",", "."))
                end = int(m.group(4)) * 3600 + int(m.group(5)) * 60 + float(m.group(6).replace(",", "."))
            else:
                m = re.match(r"(\d+):(\d+[.,]\d+)\s*-->\s*(\d+):(\d+[.,]\d+)", ts_line)
                if not m:
                    continue
                start = int(m.group(1)) * 60 + float(m.group(2).replace(",", "."))
                end = int(m.group(3)) * 60 + float(m.group(4).replace(",", "."))

            seg_text = re.sub(r"<[^>]+>", "", " ".join(text_lines)).strip()
            if seg_text:
                segments.append({
                    "text": seg_text,
                    "start": start,
                    "duration": max(0.0, end - start),
                })
        return segments

    def _fetch_fallback(self, video_id: str) -> dict | None:
        try:
            from youtube_transcript_api import (
                NoTranscriptFound,
                TranscriptsDisabled,
                YouTubeTranscriptApi,
            )
        except ImportError:
            return None

        try:
            api = YouTubeTranscriptApi()
            transcript_list = api.list(video_id)

            transcript = None
            used_language = None
            is_generated = False

            for lang in self.preferred_languages:
                try:
                    transcript = transcript_list.find_manually_created_transcript([lang])
                    used_language = lang
                    break
                except NoTranscriptFound:
                    continue

            if transcript is None:
                for lang in self.preferred_languages:
                    try:
                        transcript = transcript_list.find_generated_transcript([lang])
                        used_language = lang
                        is_generated = True
                        break
                    except NoTranscriptFound:
                        continue

            if transcript is None:
                available = list(transcript_list)
                if available:
                    transcript = available[0]
                    used_language = transcript.language_code
                    is_generated = transcript.is_generated

            if transcript is None:
                return None

            fetched = transcript.fetch()
            full_text = " ".join(
                seg.text.replace("\n", " ").strip()
                for seg in fetched
                if seg.text.strip()
            )
            return {
                "video_id": video_id,
                "language": used_language,
                "is_generated": is_generated,
                "full_text": full_text,
                "segments": [
                    {
                        "text": seg.text,
                        "start": seg.start,
                        "duration": seg.duration,
                    }
                    for seg in fetched
                ],
            }

        except Exception:
            return None
