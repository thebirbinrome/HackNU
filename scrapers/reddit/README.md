# Reddit Claude AI Scraper

Hackathon tool to collect public Reddit discourse about Claude AI using Reddit's
public JSON API — no API key, no authentication, no PRAW required.

## What it collects

| Field | Description |
|---|---|
| `id` | Reddit post ID (used for deduplication) |
| `subreddit` | Subreddit name |
| `title` | Post title |
| `score` | Net upvotes |
| `num_comments` | Comment count |
| `created_utc` | Post date (ISO-8601 UTC) |
| `author` | Username (or `[deleted]`) |
| `url` | Link URL |
| `selftext` | First 500 chars of post body |
| `flair` | Post flair (empty string if none) |
| `upvote_ratio` | Upvote ratio (0.0–1.0) |
| `permalink` | Full Reddit permalink |
| `source_query` | Which scrape phase found this post |

**Subreddits:** r/ClaudeAI, r/ChatGPT, r/artificial, r/LocalLLaMA, r/singularity

**Queries searched:** "Claude", "Claude AI", "Claude vs ChatGPT", "Claude Code", "Anthropic", "#QuitGPT"

## Setup

```bash
# Python 3.8+ required
pip install requests
```

No other dependencies — everything else is standard library.

## Run

```bash
cd scrapers/reddit
python reddit_scraper.py
```

Progress is logged to both stdout and `scraper.log`.

## Output files

| File | Description |
|---|---|
| `reddit_claude_data.csv` | Full dataset, one row per post |
| `reddit_summary.json` | Totals, subreddit breakdown, date range, top 10 posts |
| `scraper.log` | Timestamped run log |

## How it works

1. **Phase 1 — Top posts:** Fetches top posts for each subreddit across three
   time windows (all-time, past year, past month) using `/r/<sub>/top.json`.
   Paginates via the `after` token, up to 10 pages (~250 posts) per window.

2. **Phase 2 — Search:** Runs each query against each subreddit via
   `/r/<sub>/search.json` with two sort modes (relevance + new) to maximise
   coverage.

3. **Deduplication:** A global `seen` dict keyed on post ID prevents duplicates
   regardless of which phase or query found the post.

4. **Rate limiting:** A minimum 1.2-second delay between every request.
   HTTP 429/503 responses trigger exponential back-off (2^n seconds, up to 3
   retries).

## Known limitations

- Reddit's listing endpoints hard-cap at ~1000 posts; combining phases works
  around this.
- Search results are capped at ~250 per query by Reddit's backend.
- Deleted/removed posts appear as `[deleted]` / `[removed]` — filter downstream
  if needed.
- Very new subreddits or sparse queries may yield fewer than 500 posts total.

## Ethical notes

- Public data only — no login-wall scraping, no private messages, no DMs.
- Respects Reddit's public API rate-limit guidance (≥1 req/s).
- User-Agent identifies the scraper as hackathon research.
