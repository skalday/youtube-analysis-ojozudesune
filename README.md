# YouTube Channel Analysis Tool

Fetch transcripts and comments from a YouTube channel, then use an LLM to analyse audience profiles, brand positioning, and build a structured knowledge database.

## Features

- **Transcript fetching** — pulls subtitles for all channel videos via `youtube-transcript-api`, with language priority fallback (manual → auto-generated)
- **Comment fetching** — retrieves top comments per video via YouTube Data API v3
- **Audience analysis** — infers viewer demographics, sentiment, interests, and engagement patterns from comments
- **Brand analysis** — analyses channel tone, positioning, and content themes from transcripts
- **Knowledge index** — builds a per-video index of golf tips and techniques
- **Dual LLM backend** — use Claude API (cloud) or a local Ollama model; switchable per run
- **Incremental cache** — only new videos are fetched on subsequent runs; existing data is reused

---

## Installation

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and fill in the relevant values:

```env
# Required
YOUTUBE_API_KEY=...          # YouTube Data API v3 key
                             # https://console.cloud.google.com/apis/credentials

# Required only when using --llm claude (default)
ANTHROPIC_API_KEY=...        # https://console.anthropic.com/

# Optional overrides
DEFAULT_CHANNEL_ID=@handle   # Default channel if --channel is omitted
MAX_VIDEOS=120               # Default video limit
MAX_COMMENTS_PER_VIDEO=100

CLAUDE_MODEL=claude-sonnet-4-6
CLAUDE_MAX_TOKENS=8096

# Local LLM (Ollama)
LOCAL_LLM_URL=http://localhost:11434/v1
LOCAL_LLM_MODEL=gemma3:12b
```

---

## Usage

### Basic run (Claude API)

```bash
python main.py --channel @ChannelHandle
```

### Use local Ollama model instead

```bash
# Uses LOCAL_LLM_MODEL from .env (default: gemma3:12b)
python main.py --channel @ChannelHandle --llm local

# Override model for this run
python main.py --channel @ChannelHandle --llm local --llm-model qwen2.5:32b
```

### Common options

```bash
# Analyse 50 videos, fetch up to 200 comments each
python main.py --channel @ChannelHandle --max-videos 50 --max-comments 200

# Force re-fetch all data (ignore cache)
python main.py --channel @ChannelHandle --force-refresh

# Transcripts + brand analysis only (skip comments)
python main.py --channel @ChannelHandle --skip-comments

# Comments + audience analysis only (skip transcripts)
python main.py --channel @ChannelHandle --skip-transcripts

# Skip location/knowledge extraction (faster, audience + brand only)
python main.py --channel @ChannelHandle --skip-extraction

# Refresh comments for already-cached videos
python main.py --channel @ChannelHandle --refresh-comments
```

### Full CLI reference (`main.py`)

| Flag | Description | Default |
|------|-------------|---------|
| `--channel` | YouTube channel `@handle` or channel ID (required) | — |
| `--llm` | LLM backend: `claude` or `local` (Ollama) | `claude` |
| `--llm-model` | Override model name for this run | from `.env` |
| `--max-videos` | Maximum videos to analyse | `20` |
| `--max-comments` | Maximum comments per video | `500` |
| `--force-refresh` | Ignore all cache and re-fetch everything | `false` |
| `--refresh-comments` | Re-fetch comments for cached videos | `false` |
| `--retry-failed-transcripts` | Re-fetch transcripts that previously failed (no file saved) | `false` |
| `--video` | Fetch transcript for a single video ID, skips channel list fetch | — |
| `--skip-transcripts` | Skip transcript fetching and related analyses | `false` |
| `--skip-comments` | Skip comment fetching and audience analysis | `false` |
| `--skip-extraction` | Skip location/knowledge extraction (audience + brand only, much faster) | `false` |
| `--output-dir` | Report output root directory | `./reports` |

---

## Offline analysis (no YouTube API needed)

If data has already been collected and saved under `data/`, use `analyze_local.py` to run LLM analysis directly on the cached files — no YouTube API key required.

```bash
# Audience + brand analysis only (fastest)
python analyze_local.py --channel-id UCxxxxxxxxxx --llm local --skip-extraction

# Full analysis including location / knowledge extraction
python analyze_local.py --channel-id UCxxxxxxxxxx --llm local

# Use a specific Ollama model
python analyze_local.py --channel-id UCxxxxxxxxxx --llm local --model gemma3:12b

# Limit to the N most recent videos
python analyze_local.py --channel-id UCxxxxxxxxxx --llm local --max-videos 20

# Use Claude API instead of local
python analyze_local.py --channel-id UCxxxxxxxxxx --llm claude
```

### Full CLI reference (`analyze_local.py`)

| Flag | Description | Default |
|------|-------------|---------|
| `--channel-id` | Channel ID from the `data/` directory (required) | — |
| `--data-dir` | Base data directory | `./data` |
| `--output-dir` | Report output root directory | `./reports` |
| `--llm` | LLM backend: `claude` or `local` (Ollama) | `local` |
| `--model` | Override model name (e.g. `gemma3:12b`, `qwen3:8b`) | `qwen3:8b` |
| `--ollama-url` | Ollama API base URL | `http://localhost:11434/v1` |
| `--max-videos` | Limit number of videos included in analysis | all |
| `--skip-audience` | Skip audience analysis (comments) | `false` |
| `--skip-brand` | Skip brand analysis (transcripts) | `false` |
| `--skip-extraction` | Skip location/knowledge extraction — runs only audience + brand, much faster | `false` |

---

## Output

### Report files

Files generated depend on which flags are used:

```
reports/{channel_id}/
├── audience_report.md       # Audience profile — generated unless --skip-comments / --skip-audience
├── brand_report.md          # Brand positioning  — generated unless --skip-transcripts / --skip-brand
├── comments.csv             # Raw comments export — generated unless --skip-comments / --skip-audience
├── transcripts.csv          # Raw transcripts export — generated unless --skip-transcripts / --skip-brand
├── summary.json             # Aggregated stats + analysis snapshots (always written)
│
│   # The following are only generated when extraction is NOT skipped
│   # (i.e. --skip-extraction is NOT set)
├── knowledge_index.md       # Knowledge index with video links
├── knowledge_index.csv      # Knowledge index (filterable in Excel)
├── locations_database.json  # Full location / food / equipment database
├── locations_database.csv   # Locations (importable to Google My Maps)
├── food_database.csv        # Food items mentioned across videos
└── equipment_database.csv   # Equipment / gear mentioned
```

### Raw data cache

```
data/
├── raw/
│   ├── videos/{channel_id}/video_list.json      # Video metadata
│   ├── transcripts/{channel_id}/{video_id}.json # Per-video transcript
│   └── comments/{channel_id}/{video_id}.json    # Per-video comments
└── processed/
    └── {analysis_type}/{channel_id}/result.json
```

Cached data is reused on subsequent runs — only new videos trigger API calls.

---

## Project structure

```
├── main.py              # CLI entry point (fetch + analyse, requires YouTube API)
├── analyze_local.py     # Offline analysis on cached data (no YouTube API needed)
├── config/              # Settings and .env loader
├── collectors/          # YouTube Data API + transcript fetching
├── analyzers/           # LLM clients (Claude / Ollama) + audience/brand analysis
├── extractors/          # Structured extraction (locations, knowledge)
├── reporters/           # Output writers (Markdown / JSON / CSV)
└── storage/             # Local cache management
```
