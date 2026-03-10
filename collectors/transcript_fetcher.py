from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound, TranscriptsDisabled
from tqdm import tqdm


class TranscriptFetcher:
    def __init__(self, preferred_languages: list | None = None):
        self.preferred_languages = preferred_languages or ["ja", "zh-Hant", "zh-Hans", "en"]

    def fetch(self, video_id: str) -> dict | None:
        """
        Fetch transcript for a single video.
        Returns dict or None if unavailable.
        """
        try:
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)

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

            segments = transcript.fetch()
            full_text = " ".join(
                seg.get("text", "").replace("\n", " ").strip()
                for seg in segments
                if seg.get("text", "").strip()
            )

            return {
                "video_id": video_id,
                "language": used_language,
                "is_generated": is_generated,
                "full_text": full_text,
                "segments": [
                    {
                        "text": seg.get("text", ""),
                        "start": seg.get("start", 0),
                        "duration": seg.get("duration", 0),
                    }
                    for seg in segments
                ],
            }

        except TranscriptsDisabled:
            return None
        except Exception:
            return None

    def fetch_batch(self, video_ids: list, skip_existing_ids: set | None = None) -> dict:
        """
        Fetch transcripts for multiple videos.
        Returns {video_id: transcript_dict_or_None}
        """
        results = {}
        skip = skip_existing_ids or set()

        to_fetch = [vid for vid in video_ids if vid not in skip]

        for video_id in tqdm(to_fetch, desc="Fetching transcripts", unit="vid"):
            results[video_id] = self.fetch(video_id)

        return results
