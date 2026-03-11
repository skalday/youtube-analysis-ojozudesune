import logging
from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound, TranscriptsDisabled
from youtube_transcript_api._errors import (
    VideoUnavailable,
    IpBlocked,
    RequestBlocked,
)
try:
    from youtube_transcript_api._errors import PoTokenRequired
    _POT_REQUIRED_AVAILABLE = True
except ImportError:
    _POT_REQUIRED_AVAILABLE = False

from tqdm import tqdm

logger = logging.getLogger(__name__)


class TranscriptFetcher:
    def __init__(self, languages: list | None = None, store=None):
        self.preferred_languages = languages or ["ja", "zh-Hant", "zh-Hans", "en"]
        self.store = store
        self._api = YouTubeTranscriptApi()  # v1.x: instance-based API

    def fetch(self, video_id: str) -> dict | None:
        """
        Fetch transcript for a single video.
        Returns dict or None if unavailable.
        """
        try:
            transcript_list = self._api.list(video_id)  # v1.x: api.list()

            transcript = None
            used_language = None
            is_generated = False

            # Try preferred languages in order (manual first)
            for lang in self.preferred_languages:
                try:
                    transcript = transcript_list.find_manually_created_transcript([lang])
                    used_language = lang
                    is_generated = False
                    break
                except NoTranscriptFound:
                    continue

            # Fallback to auto-generated
            if transcript is None:
                for lang in self.preferred_languages:
                    try:
                        transcript = transcript_list.find_generated_transcript([lang])
                        used_language = lang
                        is_generated = True
                        break
                    except NoTranscriptFound:
                        continue

            # Last resort: any available transcript
            if transcript is None:
                try:
                    available = list(transcript_list)
                    if available:
                        transcript = available[0]
                        used_language = transcript.language_code
                        is_generated = transcript.is_generated
                except Exception:
                    return None

            if transcript is None:
                return None

            # v1.x: fetch() returns FetchedTranscript; snippets are dataclasses
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

        except TranscriptsDisabled:
            logger.debug("Transcripts disabled for video %s", video_id)
            return None
        except VideoUnavailable:
            logger.debug("Video unavailable: %s", video_id)
            return None
        except IpBlocked:
            logger.warning(
                "IP blocked by YouTube while fetching transcript for %s. "
                "Consider using a proxy.",
                video_id,
            )
            return None
        except RequestBlocked:
            logger.warning(
                "Request blocked by YouTube while fetching transcript for %s. "
                "Consider using a proxy or waiting before retrying.",
                video_id,
            )
            return None
        except Exception as exc:
            # PoTokenRequired may not exist in all v1.x minor releases; handle by name
            if type(exc).__name__ == "PoTokenRequired":
                logger.warning(
                    "YouTube requires a proof-of-origin token (PoToken) for video %s. "
                    "Transcript unavailable in this environment.",
                    video_id,
                )
                return None
            logger.warning("Failed to fetch transcript for %s: %s", video_id, exc)
            return None

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
