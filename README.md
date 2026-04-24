# YouTube Channel Analysis Tool

Fetch transcripts and comments from a YouTube channel, then use a local LLM (Ollama) to analyse audience profiles and brand positioning. Results are displayed in a browser-based web UI and saved as Markdown reports.

## Features

| Feature | Description |
|---------|-------------|
| Audience profile analysis | Infer audience age, interests, pain points, and language patterns from comments |
| Brand positioning analysis | Extract content themes, communication style, and value propositions from transcripts |
| Incremental updates | Fetch only videos published since the last run; cached data is reused automatically |
| Channel management | View, re-analyse, or delete any previously analysed channel from the UI |
| Web UI | Browser interface with real-time progress streaming |

---

## Prerequisites

### 1. Ollama (local LLM)

1. Install Ollama from [ollama.com](https://ollama.com)
2. Pull a model:
   ```bash
   ollama pull gemma3:12b
   ```

### 2. YouTube Data API v3 key

1. Go to [Google Cloud Console](https://console.cloud.google.com/apis/credentials)
2. Create a project → Enable **YouTube Data API v3** → Create an API key

### 3. Python dependencies

```bash
pip install -r requirements.txt
```

### 4. `.env` file

Create a `.env` file in the project root:

```
YOUTUBE_API_KEY=your_key_here
LOCAL_LLM_URL=http://localhost:11434/v1   # optional, this is the default
```

---

## Quick Start

**Windows:** double-click `start.bat`

**Manual:**
```bash
# Make sure Ollama is already running, then:
python server.py
```

Open `http://localhost:5000` in your browser.

---

## Usage

### Analysing a new channel

1. Select an Ollama model from the dropdown
2. Enter a channel handle (e.g. `@ChannelName`) or channel ID
3. Set the maximum number of videos to analyse
4. Optionally skip audience or brand analysis
5. Click **開始抓取並分析**

### Managing existing channels

Select a channel from the dropdown, then use the action buttons:

| Button | What it does |
|--------|-------------|
| 查看結果 | Load and display the last analysis results |
| 補抓並分析 | Fetch videos published since the last run, then re-analyse |
| 直接分析 | Re-run analysis on existing cached data (no new fetch) |
| 僅補抓 | Fetch new videos and save to cache, without running analysis |
| 刪除 | Delete all data and reports for this channel |

---

## Output files (`reports/<channel_id>/`)

| File | Description |
|------|-------------|
| `summary.json` | Channel metadata and stats used by the web UI |
| `audience_report.md` | Audience profile report |
| `brand_report.md` | Brand positioning report |
| `comments.csv` | All fetched comments |
| `transcripts.csv` | All fetched transcripts |

Raw data is cached in `data/raw/` and reused on subsequent runs.

---

## `.env` reference

| Variable | Description | Default |
|----------|-------------|---------|
| `YOUTUBE_API_KEY` | YouTube Data API v3 key **(required)** | — |
| `LOCAL_LLM_URL` | Ollama API base URL | `http://localhost:11434/v1` |
| `MAX_VIDEOS` | Default maximum videos to fetch | `20` |
| `MAX_COMMENTS_PER_VIDEO` | Maximum comments per video | `100` |
| `TRANSCRIPT_LANGUAGES` | Language priority (comma-separated) | `ja,zh-Hant,zh-Hans,en` |
| `DATA_DIR` | Raw data cache directory | `./data` |
| `REPORTS_DIR` | Report output directory | `./reports` |

---

## Project structure

```
├── server.py                     # Flask backend + API endpoints
├── index.html                    # Web UI frontend
├── start.bat                     # Windows launcher (starts Ollama + Flask + browser)
├── config/
│   └── settings.py               # Settings dataclass + .env loader
└── modules/
    ├── fetcher.py                 # Fetch orchestration (full + incremental)
    ├── analyzer.py                # Analysis orchestration + report writing
    ├── analysis/
    │   ├── audience.py            # Audience profile LLM prompt + parser
    │   └── brand.py               # Brand positioning LLM prompt + parser
    ├── collectors/
    │   ├── youtube_api.py         # YouTube Data API client (video list + incremental)
    │   ├── transcript.py          # Transcript fetcher
    │   └── comments.py            # Comment fetcher
    ├── llm_providers/
    │   ├── base.py                # BaseLLMClient interface
    │   └── local_llm.py           # Ollama client
    ├── reporters/
    │   ├── markdown.py            # Markdown report writer
    │   └── csv_reporter.py        # CSV export writer
    └── storage/
        ├── file_store.py          # JSON / CSV read-write
        └── cache.py               # Cache helpers
```

---

## Troubleshooting

**Model dropdown shows "無可用模型"**
Ollama is not running or has no models installed. Run `ollama pull gemma3:12b` and restart the server.

**Analysis fails with quota error**
The YouTube Data API has a daily quota. Wait until the next day or create a new API key.

**Prompt truncation / slow analysis**
Use a model with a larger context window, or reduce the number of videos analysed.

**Chinese characters appear as gibberish**
Run `chcp 65001` in your terminal before starting, or use `start.bat` which sets this automatically.
