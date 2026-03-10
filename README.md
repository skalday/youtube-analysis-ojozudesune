# YouTube 頻道分析工具

從指定 YouTube 頻道抓取影片逐字稿和留言，透過 Claude AI 分析觀眾 TA 輪廓、個人品牌定位，並建立地點資料庫和知識索引。

## 功能

| 功能 | 說明 |
|------|------|
| TA 輪廓分析 | 從留言推斷受眾年齡層、興趣、痛點、語言習慣 |
| 品牌定位分析 | 從逐字稿提取內容主題、溝通風格、價值主張 |
| 地點/食物/設備資料庫 | 萃取每集提到的球場、餐廳、設備，可匯入 Google My Maps |
| 高爾夫知識索引 | 整理每集的知識和技巧，附影片連結可直接引用 |
| 滾動更新 | 自動偵測新影片，增量抓取，保留歷史分析快照 |

## 快速開始

### 1. 安裝依賴

```bash
pip install -r requirements.txt
```

### 2. 設定 API Keys

```bash
cp .env.example .env
# 編輯 .env，填入 YOUTUBE_API_KEY 和 ANTHROPIC_API_KEY
```

**取得 API Keys：**
- YouTube Data API v3：[Google Cloud Console](https://console.cloud.google.com/apis/credentials) → 啟用 YouTube Data API v3
- Anthropic API：[console.anthropic.com](https://console.anthropic.com/)

### 3. 執行分析

```bash
# 基本用法
python main.py --channel @頻道名稱

# 分析 30 支影片，每支抓 200 則留言
python main.py --channel @頻道名稱 --max-videos 30 --max-comments 200

# 強制重新抓取（忽略快取）
python main.py --channel @頻道名稱 --force-refresh

# 只做知識萃取，跳過留言分析
python main.py --channel @頻道名稱 --skip-comments

# 更新已快取影片的最新留言
python main.py --channel @頻道名稱 --refresh-comments
```

## 輸出檔案

```
reports/{channel_id}/
├── audience_report.md       # TA 輪廓分析報告（繁體中文）
├── brand_report.md          # 品牌定位分析報告（繁體中文）
├── knowledge_index.md       # 高爾夫知識索引（附影片連結）
├── knowledge_index.csv      # 知識索引表格（可 Excel 篩選）
├── locations_database.json  # 地點/食物/設備完整資料庫
├── locations_database.csv   # 地點 CSV（可匯入 Google My Maps）
├── comments.csv             # 原始留言匯出
├── transcripts.csv          # 原始逐字稿匯出
└── summary.json             # 整合指標 + 歷史分析快照
```

## CLI 參數說明

| 參數 | 說明 | 預設值 |
|------|------|--------|
| `--channel` | YouTube 頻道 @handle 或 ID（必填） | — |
| `--max-videos` | 最多分析幾支影片 | 20 |
| `--max-comments` | 每支影片最多幾則留言 | 100 |
| `--force-refresh` | 忽略所有快取，重新抓取 | False |
| `--refresh-comments` | 只更新留言快取（逐字稿不動） | False |
| `--skip-transcripts` | 跳過逐字稿相關分析 | False |
| `--skip-comments` | 跳過留言相關分析 | False |
| `--output-dir` | 報告輸出目錄 | `./reports` |

## 滾動更新

頻道有新影片時，直接重新執行同一指令即可：

```bash
python main.py --channel @頻道名稱
```

- 已抓取的影片**直接讀快取**，不重複呼叫 API
- 只抓取**新影片**的逐字稿和留言
- 每次分析結果追加到 `summary.json` 的 `analysis_history`，可對比前後變化

## 專案結構

```
├── config/          # 設定載入
├── collectors/      # YouTube API 資料抓取
├── storage/         # 本地快取管理
├── analyzers/       # Claude AI 分析（TA + 品牌）
├── extractors/      # 結構化知識萃取（地點 + 知識）
├── reporters/       # 報告輸出（Markdown / JSON / CSV）
└── main.py          # CLI 入口點
```
