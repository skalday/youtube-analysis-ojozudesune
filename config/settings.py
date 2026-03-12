import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    youtube_api_key: str
    anthropic_api_key: str
    default_channel_id: str
    max_videos: int
    max_comments_per_video: int
    cache_ttl_hours: int
    transcript_languages: list
    llm_backend: str
    claude_model: str
    claude_max_tokens: int
    local_llm_url: str
    local_llm_model: str
    data_dir: str
    reports_dir: str


def load_settings() -> Settings:
    youtube_api_key = os.getenv("YOUTUBE_API_KEY", "")
    anthropic_api_key = os.getenv("ANTHROPIC_API_KEY", "")

    if not youtube_api_key:
        raise ValueError("YOUTUBE_API_KEY is not set. Please check your .env file.")

    raw_langs = os.getenv("TRANSCRIPT_LANGUAGES", "ja,zh-Hant,zh-Hans,en")
    transcript_languages = [lang.strip() for lang in raw_langs.split(",") if lang.strip()]

    return Settings(
        youtube_api_key=youtube_api_key,
        anthropic_api_key=anthropic_api_key,
        default_channel_id=os.getenv("DEFAULT_CHANNEL_ID", ""),
        max_videos=int(os.getenv("MAX_VIDEOS", "20")),
        max_comments_per_video=int(os.getenv("MAX_COMMENTS_PER_VIDEO", "100")),
        cache_ttl_hours=int(os.getenv("CACHE_TTL_HOURS", "24")),
        transcript_languages=transcript_languages,
        llm_backend=os.getenv("LLM_BACKEND", "claude"),
        claude_model=os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6"),
        claude_max_tokens=int(os.getenv("CLAUDE_MAX_TOKENS", "8096")),
        local_llm_url=os.getenv("LOCAL_LLM_URL", "http://localhost:11434/v1"),
        local_llm_model=os.getenv("LOCAL_LLM_MODEL", "qwen2.5:latest"),
        data_dir=os.getenv("DATA_DIR", "./data"),
        reports_dir=os.getenv("REPORTS_DIR", "./reports"),
    )
