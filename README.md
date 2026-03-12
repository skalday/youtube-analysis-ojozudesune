# YouTube Channel Analysis Tool

Fetch transcripts and comments from a YouTube channel, then use Claude AI to analyse audience profiles, brand positioning, and build a location/knowledge database.

## Features

| Feature | Description |
|---------|-------------|
| Audience profile analysis | Infer audience age, interests, pain points, and language patterns from comments |
| Brand positioning analysis | Extract content themes, communication style, and value propositions from transcripts |
| Knowledge index | Organise knowledge and tips per episode with video links for direct reference |
| Incremental updates | Auto-detect new videos, fetch only new data, preserve historical analysis snapshots |

---

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure API keys

```bash
cp .env.example .env
# Edit .env and fill in YOUTUBE_API_KEY and ANTHROPIC_API_KEY (or LLM_BACKEND=local)
```

**How to get API keys:**
- YouTube Data API v3: [Google Cloud Console](https://console.cloud.google.com/apis/credentials) → Enable YouTube Data API v3
- Anthropic API: [console.anthropic.com](https://console.anthropic.com/)

### 3. Run full analysis

```bash
python main.py --channel @ChannelHandle
```

### CLI reference

```bash
python main.py --channel @ChannelHandle
python main.py --channel UCxxxxxxxxxx
```

| Flag | Description |
|------|-------------|
| `--channel` | YouTube channel @handle or Channel ID (required) |

All other options are set in `.env` (copy from `.env.example`):

| `.env` variable | Description | Default |
|-----------------|-------------|---------|
| `LLM_BACKEND` | `claude` or `local` (Ollama) | `claude` |
| `CLAUDE_MODEL` | Claude model name | `claude-sonnet-4-6` |
| `LOCAL_LLM_MODEL` | Ollama model name | `gemma3:12b` |
| `LOCAL_LLM_URL` | Ollama API base URL | `http://localhost:11434/v1` |
| `MAX_VIDEOS` | Maximum videos to fetch and analyse | `50` |
| `MAX_COMMENTS_PER_VIDEO` | Maximum comments per video | `100` |
| `TRANSCRIPT_LANGUAGES` | Language priority (comma-separated) | `ja,zh-Hant,zh-Hans,en` |
| `DATA_DIR` | Raw data cache directory | `./data` |
| `REPORTS_DIR` | Report output directory | `./reports` |

---

## Offline analysis

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

---

## Output

### Report files

Files generated depend on which flags are used:

```
reports/{channel_id}/
├── audience_report.md       # Audience profile — generated unless --skip-comments / --skip-audience
├── brand_report.md          # Brand positioning  — generated unless --skip-transcripts / --skip-brand
├── comments.csv             # Raw comments export
├── transcripts.csv          # Raw transcripts export
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
data/{channel_id}/
├── videos.json              # Video metadata list
├── transcripts/{video_id}.json
└── comments/{video_id}.json
```

Cached data is reused on subsequent runs — only new videos trigger API calls.

---

## Incremental updates

When the channel has new videos, just re-run the same command:

```bash
python main.py --channel @ChannelHandle
```

- Already-fetched videos are **read from cache** — no redundant API calls
- Only **new videos** have their transcripts and comments fetched
- Each run appends a snapshot to `summary.json`'s `analysis_history` for tracking changes over time

---

## Project structure

```
├── main.py              # CLI entry point (fetch + analyse, requires YouTube API)
├── analyze_local.py     # Offline analysis on cached data (no YouTube API needed)
├── config/              # Settings and .env loader
├── collectors/          # YouTube Data API + transcript fetching
├── analyzers/           # LLM clients (Claude / Ollama) + audience/brand analysis
├── extractors/          # Location / knowledge structured extraction
├── reporters/           # Markdown / JSON / CSV output
└── storage/             # Local cache management
```
