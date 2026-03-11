# YouTube Channel Analysis Tool

Fetch transcripts and comments from a YouTube channel, then use Claude AI to analyse audience profiles, brand positioning, and build a location/knowledge database.

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure API keys

```bash
cp .env.example .env
# Edit .env and fill in YOUTUBE_API_KEY and ANTHROPIC_API_KEY
```

**How to get API keys:**
- YouTube Data API v3: [Google Cloud Console](https://console.cloud.google.com/apis/credentials) 
- Anthropic API: [console.anthropic.com](https://console.anthropic.com/)

### 3. Preview data size and estimated cost (no Claude API calls)

```bash
python main.py --channel @ChannelHandle --data-only
```

This fetches transcripts and comments, then prints a token count and cost estimate for each analysis type without spending any Claude API credits.

### 4. Run full analysis

```bash
# Basic usage
python main.py --channel @ChannelHandle

# Analyse 30 videos, fetch 200 comments each
python main.py --channel @ChannelHandle --max-videos 30 --max-comments 200

# Force re-fetch (ignore cache)
python main.py --channel @ChannelHandle --force-refresh

# Skip comment analysis (brand analysis only)
python main.py --channel @ChannelHandle --skip-comments

# Update cached comments to latest
python main.py --channel @ChannelHandle --refresh-comments
```

## Output files

```
reports/{channel_id}/
├── audience_report.md       # Audience profile report
├── brand_report.md          # Brand positioning report
├── knowledge_index.md       # Golf knowledge index (with video links)
├── knowledge_index.csv      # Knowledge index table (filterable in Excel)
├── locations_database.json  # Full location / food / equipment database
├── locations_database.csv   # Locations CSV (importable to Google My Maps)
├── food_database.csv        # Food items CSV
├── equipment_database.csv   # Equipment CSV
├── comments.csv             # Raw comments export
├── transcripts.csv          # Raw transcripts export
└── summary.json             # Aggregated stats + historical analysis snapshots
```

## CLI reference

| Flag | Description | Default |
|------|-------------|---------|
| `--channel` | YouTube channel @handle or ID (required) | — |
| `--max-videos` | Maximum videos to analyse | 20 |
| `--max-comments` | Maximum comments per video | 100 |
| `--data-only` | Fetch data only, print token/cost estimate, no Claude calls | False |
| `--force-refresh` | Ignore all cache and re-fetch everything | False |
| `--refresh-comments` | Re-fetch comments for cached videos only | False |
| `--skip-transcripts` | Skip transcript fetching and related analyses | False |
| `--skip-comments` | Skip comment fetching and audience analysis | False |
| `--skip-extraction` | Skip location/knowledge extraction (audience + brand only) | False |
| `--output-dir` | Report output directory | `./reports` |

## Incremental updates

When the channel has new videos, just re-run the same command:

```bash
python main.py --channel @ChannelHandle
```

- Already-fetched videos are **read from cache** — no redundant API calls
- Only **new videos** have their transcripts and comments fetched
- Each run appends a snapshot to `summary.json`'s `analysis_history` for tracking changes over time

## Project structure

```
├── config/          # Settings loader
├── collectors/      # YouTube API data fetching
├── storage/         # Local cache management
├── analyzers/       # Claude AI analysis (audience + brand)
├── extractors/      # Structured knowledge extraction (locations + knowledge)
├── reporters/       # Report output (Markdown / JSON / CSV)
└── main.py          # CLI entry point
```
