# Claude AI Viral Growth — Data Collection & Analysis

HackNU Higgsfield Growth Management Project Submission. 
Mass Reddit thread and YouTube video Python scrapers.

## File Structure

```
scrapers/
├── reddit/
│   ├── reddit_scraper.py          # scrape + analyze function (single script)
│   ├── reddit_claude_data.csv     # ~9,000+ posts
│   ├── reddit_summary.json
│   └── charts/                    # PNG visualizations
│
└── youtube/
    ├── youtube_scraper.py         # scrape + analyze function (single script)
    ├── youtube_claude_data.csv    # ~400+ videos
    ├── youtube_summary.json
    └── charts/                    # PNG visualizations
```

## Quick start
Enter these commands into terminal
```bash
# Reddit (no API key needed)
pip install requests matplotlib seaborn pandas
cd scrapers/reddit
python reddit_scraper.py --analyze    # charts from existing data
python reddit_scraper.py              # full scrape + analyze

# YouTube (needs free API key)

pip install google-api-python-client matplotlib seaborn pandas
export YOUTUBE_API_KEY='your-key'
or
$env:YOUTUBE_API_KEY='AIzaSyC4zTM4oYECLXD3XQOeHGVDYVFzYEvNBfg'
cd scrapers/youtube
python youtube_scraper.py --analyze   # charts from existing data
python youtube_scraper.py             # full scrape + analyze
```

Both scripts support `--scrape` (collect data), `--analyze` (charts), or no flag (does both). Both resume from existing CSV if interrupted.

## What each scraper collects

| | Reddit | YouTube |
|---|---|---|
| Source | Public JSON API (no auth) | YouTube Data API v3 (free key) |
| Targets | 5 subreddits, 6 search queries | 8 search queries (expandable) |
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

Terminal insights include much more data, such as viral density peaks, most engaged communities/channels, correlation analysis, and distinctive vocabulary in viral content.

## Design decisions

- **Public data only** — no login-wall scraping, no private data, no DMs
- **Single-script per platform** — scraper and analysis combined, three run modes
- **Resume support** — existing CSV loaded on restart, deduplication by ID
- **No heavy NLP deps** — built-in stop word list, no NLTK/spaCy required
- **Graceful failure** — retries, back-off, partial data saved on interrupt


## AI Usage & Validation
This project was developed with the assistance of AI code generation tools (LLMs).

### What was AI-generated
- Initial scraper architecture (request loops, pagination, batching logic)
- Data parsing functions for Reddit JSON and YouTube API responses
- Chart generation templates (matplotlib / seaborn)
- Basic NLP logic (tokenization, stop-word filtering, word frequency comparison)

### What we manually validated
Each component was tested and verified:

**1. Data correctness** Cross-checked sampled Reddit posts and YouTube videos manually in browser

**2. Edge cases** Tested handling of deleted posts (`[deleted]`, `[removed]`) and resolved HTTP 429 errors

**3. Rate limiting & robustness** Simulated and made up for API limits (Reddit 429 / YouTube quota exhaustion)
