# Reddit Scraper

Collects public Reddit discourse about Claude AI via the public JSON API (no API key, no PRAW, no auth), then runs analysis and generates charts.

## Setup

```bash
pip install requests matplotlib seaborn pandas
```

## Usage

```bash
python reddit_scraper.py              # scrape + analyze
python reddit_scraper.py --scrape     # scrape only
python reddit_scraper.py --analyze    # analyze only (reuses existing CSV)
```

Resumes automatically if interrupted — loads existing CSV on restart and skips already-collected posts.

## What it scrapes

**Subreddits:** r/ClaudeAI, r/ChatGPT, r/artificial, r/LocalLLaMA, r/singularity

**Method:** Top posts (all-time / year / month) + search for 6 queries ("Claude", "Claude AI", "Claude vs ChatGPT", "Claude Code", "Anthropic", "#QuitGPT") with two sort modes each. Deduplicates by post ID.

**Rate limiting:** 5s delay between requests, exponential back-off on HTTP 429/503.

## Fields collected

`id`, `subreddit`, `title`, `score`, `num_comments`, `created_utc`, `author`, `url`, `selftext` (first 500 chars), `flair`, `upvote_ratio`, `permalink`, `source_query`

## Output

| File | What |
|---|---|
| `reddit_claude_data.csv` | Full dataset, one row per post |
| `reddit_summary.json` | Totals, subreddit breakdown, date range, top 10 |
| `scraper.log` | Timestamped run log |
| `charts/01_monthly_post_count.png` | Posts per month |
| `charts/02_monthly_engagement.png` | Total score per month + post volume |
| `charts/03_top_subreddits_by_score.png` | Top 10 subreddits by total upvotes |
| `charts/04_engagement_vs_controversy.png` | Upvote ratio vs comments scatter |
| `charts/05_title_word_comparison.png` | Title words: top 100 posts vs rest |

## Limitations

- Reddit caps listings at ~1000 posts and search at ~250 per query
- Deleted posts show as `[deleted]` / `[removed]`
- Public data only, no login-wall scraping
