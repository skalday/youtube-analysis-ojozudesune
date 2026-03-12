# YouTube Channel Analysis Tool

Fetch transcripts and comments from a YouTube channel, then use Claude AI to analyse audience profiles, brand positioning, and build a location/knowledge database.

## Features

| Feature | Description |
|---------|-------------|
| Audience profile analysis | Infer audience age, interests, pain points, and language patterns from comments |
| Brand positioning analysis | Extract content themes, communication style, and value propositions from transcripts |
| Location / food / equipment database | Extract golf courses, restaurants, and gear mentioned per episode — importable to Google My Maps |
| Golf knowledge index | Organise knowledge and tips per episode with video links for direct reference |
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

### 3. Run

```bash
# Fetch data + analyse in one step
python yt.py run --channel @ChannelHandle

# Or separately:
python yt.py fetch   --channel @ChannelHandle        # download only
python yt.py analyze --channel-id UCxxxxxxxxxx       # analyse cached data (no YouTube API)
```

---

## Commands

### `fetch` — Download data from YouTube

```bash
python yt.py fetch --channel @ChannelHandle
python yt.py fetch --channel UCxxxxxxxxxx
```

Fetches the video list, transcripts, and comments into the local cache. Requires `YOUTUBE_API_KEY`.

### `analyze` — Analyse cached data (no YouTube API needed)

```bash
# Audience + brand only (fastest)
python yt.py analyze --channel-id UCxxxxxxxxxx --llm local --skip-extraction

# Full analysis
python yt.py analyze --channel-id UCxxxxxxxxxx --llm local

# Specific model, limited videos
python yt.py analyze --channel-id UCxxxxxxxxxx --llm local --model gemma3:12b --max-videos 20

# Use Claude API
python yt.py analyze --channel-id UCxxxxxxxxxx --llm claude
```

| Flag | Description | Default |
|------|-------------|---------|
| `--channel-id` | Channel ID from the `data/` directory (required) | — |
| `--llm` | LLM backend: `claude` or `local` (Ollama) | from `.env` |
| `--model` | Model name override | from `.env` |
| `--ollama-url` | Ollama base URL | from `.env` |
| `--data-dir` | Data directory | `DATA_DIR` from `.env` or `./data` |
| `--output-dir` | Report output directory | `REPORTS_DIR` from `.env` or `./reports` |
| `--skip-audience` | Skip audience analysis | `false` |
| `--skip-brand` | Skip brand analysis | `false` |
| `--skip-extraction` | Skip location/knowledge extraction | `false` |
| `--max-videos` | Limit number of videos analysed | all |

### `run` — Fetch + analyse in one step

```bash
python yt.py run --channel @ChannelHandle
python yt.py run --channel @ChannelHandle --llm local --skip-extraction
```

Accepts all the same flags as `analyze`. Requires `YOUTUBE_API_KEY`.

---

## `.env` configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `YOUTUBE_API_KEY` | YouTube Data API v3 key (required for `fetch` / `run`) | — |
| `ANTHROPIC_API_KEY` | Anthropic API key (required when `LLM_BACKEND=claude`) | — |
| `LLM_BACKEND` | `claude` or `local` (Ollama) | `claude` |
| `CLAUDE_MODEL` | Claude model name | `claude-sonnet-4-6` |
| `LOCAL_LLM_MODEL` | Ollama model name | `qwen2.5:latest` |
| `LOCAL_LLM_URL` | Ollama API base URL | `http://localhost:11434/v1` |
| `MAX_VIDEOS` | Maximum videos to fetch | `20` |
| `MAX_COMMENTS_PER_VIDEO` | Maximum comments per video | `100` |
| `TRANSCRIPT_LANGUAGES` | Language priority (comma-separated) | `ja,zh-Hant,zh-Hans,en` |
| `DATA_DIR` | Raw data cache directory | `./data` |
| `REPORTS_DIR` | Report output directory | `./reports` |

CLI flags (`--llm`, `--model`, `--ollama-url`) override `.env` values when provided.

---

## Output

### Report files

```
reports/{channel_id}/
├── audience_report.md       # Audience profile
├── brand_report.md          # Brand positioning
├── comments.csv             # Raw comments export
├── transcripts.csv          # Raw transcripts export
├── summary.json             # Aggregated stats + analysis history
│
│   # Only generated when --skip-extraction is NOT set:
├── knowledge_index.md
├── knowledge_index.csv
├── locations_database.json
├── locations_database.csv
├── food_database.csv
└── equipment_database.csv
```

### Raw data cache

```
data/raw/
├── videos/{channel_id}/video_list.json
├── transcripts/{channel_id}/{video_id}.json
└── comments/{channel_id}/{video_id}.json
```

Cached data is reused on subsequent runs — only new videos trigger API calls.

---

## Incremental updates

Re-run `fetch` or `run` at any time:

```bash
python yt.py fetch --channel @ChannelHandle
```

- Already-fetched videos are read from cache — no redundant API calls
- Only new videos have their transcripts and comments fetched
- Each run appends a snapshot to `summary.json`'s `analysis_history`

---

## Project structure

```
├── yt.py                # CLI entry point (fetch / analyze / run)
├── config/              # Settings and .env loader
├── collectors/          # YouTube Data API + transcript fetching
├── analyzers/           # LLM clients (Claude / Ollama) + audience/brand analysis
├── extractors/          # Location / knowledge structured extraction
├── reporters/           # Markdown / JSON / CSV output
└── storage/             # Local cache management
```
