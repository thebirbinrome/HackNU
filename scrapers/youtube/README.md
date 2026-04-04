# YouTube Scraper

Collects public YouTube data about Claude AI videos via the YouTube Data API v3 (free tier), then runs analysis and generates charts.

## Setup

1. Get a free YouTube API key from [Google Cloud Console](https://console.cloud.google.com/) — enable "YouTube Data API v3", create an API key under Credentials.

2. Set the key:
```bash
# Linux/Mac
export YOUTUBE_API_KEY='your-key-here'

# Windows PowerShell
$env:YOUTUBE_API_KEY='your-key-here'
```

3. Install dependencies:
```bash
pip install google-api-python-client matplotlib seaborn pandas
```

## Usage

```bash
python youtube_scraper.py              # scrape + analyze
python youtube_scraper.py --scrape     # scrape only
python youtube_scraper.py --analyze    # analyze only (reuses existing CSV)
```

Resumes automatically if interrupted — loads existing CSV on restart and skips already-collected videos.

## What it scrapes

**Queries:** "Claude AI", "Claude vs ChatGPT", "Claude Code", "Anthropic Claude", "Claude AI review", "Claude Sonnet", "Claude coding", "#QuitGPT Claude"

**Method:** Searches each query via the API, fetches video details in batches of 50. Deduplicates by video_id. Tracks quota usage and stops gracefully before hitting the 10,000 unit daily limit.

**Quota budget:** ~100 units per search call, ~1 unit per video detail. Typically uses ~9,800 units for 300-500 videos. Resets at midnight PT.

## Fields collected

`video_id`, `title`, `channel_name`, `channel_id`, `view_count`, `like_count`, `comment_count`, `published_at`, `video_url`, `duration`, `description` (first 300 chars), `tags`

## Output

| File | What |
|---|---|
| `youtube_claude_data.csv` | Full dataset, sorted by views descending |
| `youtube_summary.json` | Totals, query breakdown, top 20 videos, top 10 channels |
| `scraper.log` | Timestamped run log |
| `charts/01_monthly_video_count.png` | Videos published per month |
| `charts/02_monthly_views.png` | Total views per month + video volume |
| `charts/03_top_channels_by_views.png` | Top 10 channels by total views |
| `charts/04_engagement_vs_scale.png` | Engagement rate vs channel size |
| `charts/05_title_word_comparison.png` | Title words: top 100 videos vs rest |

## Limitations

- 10,000 quota units/day — run once per day max
- Some videos have likes/comments disabled (stored as 0)
- YouTube search caps at ~500 results per query
- Public data only, uses official API
