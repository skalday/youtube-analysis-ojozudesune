# YouTube 頻道分析工具

## 啟動

```
start.bat       # 自動啟動 Ollama + Flask + 開瀏覽器
python server.py  # 手動啟動（Ollama 需自行先跑）
```

## 功能 → 檔案對照表

| 我想改... | 去改這個檔案 |
|-----------|-------------|
| Web UI 介面（版面、按鈕、顯示欄位） | `index.html` |
| API 端點、後端邏輯 | `server.py` |
| 觀眾分析的 LLM prompt | `modules/analysis/audience.py` |
| 品牌分析的 LLM prompt | `modules/analysis/brand.py` |
| 地點/景點萃取的 LLM prompt | `modules/extractors/locations.py` |
| 知識點萃取的 LLM prompt | `modules/extractors/knowledge.py` |
| Markdown 報告格式（.md 輸出） | `modules/reporters/markdown.py` |
| CSV 報告欄位（.csv 輸出） | `modules/reporters/csv_reporter.py` |
| YouTube 影片清單抓取 | `modules/collectors/youtube_api.py` |
| 留言抓取 | `modules/collectors/comments.py` |
| 字幕抓取 | `modules/collectors/transcript.py` |
| Ollama 連線設定、timeout | `modules/llm_providers/local_llm.py` |
| 整體分析流程（跑哪些分析、寫哪些報告） | `modules/analyzer.py` |
| 資料抓取流程（fetch 的順序） | `modules/fetcher.py` |
| 路徑、預設值、環境變數 | `config/settings.py` |

## 輸出檔案（reports/<channel_id>/）

| 檔案 | 說明 |
|------|------|
| `summary.json` | Web UI 讀取用，不是給人看的報告 |
| `audience_report.md` | 觀眾分析 Markdown |
| `brand_report.md` | 品牌定位 Markdown |
| `knowledge_index.md` | 知識點 Markdown |
| `comments.csv` | 所有留言 |
| `transcripts.csv` | 所有字幕 |
| `knowledge_index.csv` | 知識點（可搜尋） |
| `locations_database.json` | 地點/食物/器材（內部用） |

## LLM

只使用 Ollama（本機）。模型在 Web UI 的下拉選單選擇。
連線設定：`.env` 裡的 `LOCAL_LLM_URL`（預設 `http://localhost:11434/v1`）

## 資料目錄

- `data/`：爬取的原始資料（已加入 .gitignore，不進 git）
- `reports/`：分析報告輸出（已加入 .gitignore，不進 git）
