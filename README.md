# YouTube Channel Analysis Tool

Fetch transcripts and comments from a YouTube channel, then use an LLM to analyse audience profiles, brand positioning, and build a structured knowledge database.

## Features

- **Transcript fetching** — pulls subtitles for all channel videos via `youtube-transcript-api`, with language priority fallback (manual → auto-generated)
- **Comment fetching** — retrieves top comments per video via YouTube Data API v3
- **Audience analysis** — infers viewer demographics, sentiment, interests, and engagement patterns from comments
- **Brand analysis** — analyses channel tone, positioning, and content themes from transcripts
- **Knowledge index** — builds a per-video index of golf tips and techniques
- **Dual LLM backend** — use Claude API (cloud) or a local Ollama model; configured via `.env`
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

# LLM backend: "claude" (default) or "local" (Ollama)
LLM_BACKEND=claude

# Required when LLM_BACKEND=claude
ANTHROPIC_API_KEY=...
CLAUDE_MODEL=claude-sonnet-4-6

# Required when LLM_BACKEND=local
LOCAL_LLM_URL=http://localhost:11434/v1
LOCAL_LLM_MODEL=gemma3:12b

# Data fetching limits
MAX_VIDEOS=50
MAX_COMMENTS_PER_VIDEO=100
```

---

## Usage

```bash
python main.py --channel @ChannelHandle
```

That's it. All configuration (LLM backend, model, video/comment limits, output paths) is read from `.env`.

To switch between Claude and Ollama, set `LLM_BACKEND` in `.env`:

```env
LLM_BACKEND=local   # use Ollama
LLM_BACKEND=claude  # use Claude API (default)
```

---

## Output

### Report files

```
reports/{channel_id}/
├── audience_report.md       # Audience profile (demographics, sentiment, interests)
├── brand_report.md          # Brand positioning and content themes
├── knowledge_index.md       # Knowledge index with video links
├── knowledge_index.csv      # Knowledge index (filterable in Excel)
├── locations_database.json  # Full location / food / equipment database
├── locations_database.csv   # Locations (importable to Google My Maps)
├── food_database.csv        # Food items mentioned across videos
├── equipment_database.csv   # Equipment / gear mentioned
├── comments.csv             # Raw comments export
├── transcripts.csv          # Raw transcripts export
└── summary.json             # Aggregated stats + analysis history snapshots
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
├── main.py              # CLI entry point
├── config/              # Settings and .env loader
├── collectors/          # YouTube Data API + transcript fetching
├── analyzers/           # LLM clients (Claude / Ollama) + audience/brand analysis
├── extractors/          # Structured extraction (locations, knowledge)
├── reporters/           # Output writers (Markdown / JSON / CSV)
└── storage/             # Local cache management
```
