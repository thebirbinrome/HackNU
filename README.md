# Claude AI Viral Growth — Data Collection & Analysis

HackNU project. Goal: reverse-engineer how Claude AI spread across public social platforms by scraping discourse data from Reddit and YouTube, then analyzing patterns in engagement, timing, and language.

## Structure

```
scrapers/
├── reddit/
│   ├── reddit_scraper.py          # scrape + analyze (single script)
│   ├── reddit_claude_data.csv     # ~9,000+ posts
│   ├── reddit_summary.json
│   └── charts/                    # 5 PNG visualizations
│
└── youtube/
    ├── youtube_scraper.py         # scrape + analyze (single script)
    ├── youtube_claude_data.csv    # ~400+ videos
    ├── youtube_summary.json
    └── charts/                    # 5 PNG visualizations
```

## Quick start

```bash
# Reddit (no API key needed)
pip install requests matplotlib seaborn pandas
cd scrapers/reddit
python reddit_scraper.py --analyze    # charts from existing data
python reddit_scraper.py              # full scrape + analyze

# YouTube (needs free API key)
pip install google-api-python-client matplotlib seaborn pandas
export YOUTUBE_API_KEY='your-key'
cd scrapers/youtube
python youtube_scraper.py --analyze   # charts from existing data
python youtube_scraper.py             # full scrape + analyze
```

Both scripts support `--scrape` (collect only), `--analyze` (charts only), or no flag (both). Both resume from existing CSV if interrupted.

## What each scraper collects

| | Reddit | YouTube |
|---|---|---|
| Source | Public JSON API (no auth) | YouTube Data API v3 (free key) |
| Targets | 5 subreddits, 6 search queries | 8 search queries |
| Volume | ~9,000 posts | ~400 videos |
| Key metrics | score, comments, upvote_ratio | views, likes, comments |
| Rate limiting | 5s delay + exponential back-off | API quota tracking (10K/day) |

## Analysis output (per platform)

Each scraper generates 5 charts and prints terminal insights:

1. **Monthly volume** — posts/videos per month (time series)
2. **Monthly engagement** — total score/views per month (interest spikes)
3. **Top sources** — subreddits by score / channels by views
4. **Engagement scatter** — controversy vs comments / engagement vs scale
5. **Title NLP** — word frequency comparison: top 100 vs the rest

Terminal insights include viral density peaks, most engaged communities/channels, correlation analysis, and distinctive vocabulary in viral content.

## Design decisions

- **Public data only** — no login-wall scraping, no private data, no DMs
- **Single-script per platform** — scraper and analysis combined, three run modes
- **Resume support** — existing CSV loaded on restart, deduplication by ID
- **No heavy NLP deps** — built-in stop word list, no NLTK/spaCy required
- **Graceful failure** — retries, back-off, partial data saved on interrupt
