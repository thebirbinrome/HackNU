# YouTube Claude AI Content Scraper

A Python scraper that collects public data about Claude AI-related videos on YouTube using the official YouTube Data API v3 (free tier).

## Purpose

This scraper analyzes public conversations about Claude AI across YouTube to understand content trends, popular videos, and active channels discussing Claude. Data is collected for research/hackathon purposes.

## Requirements

- Python 3.7+
- YouTube API key (free tier - 10,000 quota units/day)
- ~10-15 minutes of API quota to collect 300-500 videos

## Setup

### 1. Get a YouTube API Key (Free)

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Enable the **YouTube Data API v3**:
   - Search for "YouTube Data API v3" in the API library
   - Click Enable
4. Create an API key:
   - Go to Credentials (left sidebar)
   - Click "Create Credentials" → "API Key"
   - Copy your API key
5. *(Optional)* Restrict your key to YouTube Data API for security

### 2. Install Dependencies

```bash
pip install google-api-python-client
```

Or install from requirements (if provided):
```bash
pip install -r requirements.txt
```

### 3. Set Environment Variable

```bash
export YOUTUBE_API_KEY='your-api-key-here'
```

Or on Windows (PowerShell):
```powershell
$env:YOUTUBE_API_KEY='your-api-key-here'
```

## Running the Scraper

```bash
python youtube_scraper.py
```

The script will:
1. Search for videos using 8 different Claude-related queries
2. Fetch detailed information for each video found
3. Track API quota usage and stop gracefully when limit approaches
4. Output results to CSV and JSON files
5. Print progress and quota status to console

### Expected Output

```
2026-04-04 14:32:10 - INFO - YouTube Scraper initialized
2026-04-04 14:32:10 - INFO - Starting scrape for 8 queries
2026-04-04 14:32:10 - INFO - Quota limit: 10000 units
2026-04-04 14:32:11 - INFO - Searching for: 'Claude AI'
2026-04-04 14:32:14 - INFO - Quota: 100/10000 (1%)
2026-04-04 14:32:14 - INFO - Found 50 new videos for 'Claude AI'
2026-04-04 14:32:14 - INFO - Fetching details for 50 videos...
...
2026-04-04 14:47:32 - INFO - Scrape complete. Collected 387 unique videos
2026-04-04 14:47:32 - INFO - Quota used: 8945/10000 (89.5%)
2026-04-04 14:47:33 - INFO - Saving 387 videos to youtube_claude_data.csv
2026-04-04 14:47:33 - INFO - CSV saved: youtube_claude_data.csv
2026-04-04 14:47:33 - INFO - Saving summary to youtube_summary.json
2026-04-04 14:47:33 - INFO - Summary saved: youtube_summary.json
2026-04-04 14:47:33 - INFO - All done!
```

## Output Files

### `youtube_claude_data.csv`
Main dataset with all collected videos, sorted by view_count (highest first).

**Columns:**
- `video_id` - YouTube video ID
- `title` - Video title
- `channel_name` - Channel name
- `channel_id` - Channel ID
- `view_count` - Number of views
- `like_count` - Number of likes
- `comment_count` - Number of comments
- `published_at` - Publication date (ISO 8601)
- `video_url` - Full YouTube link
- `duration` - Video duration (ISO 8601 format)
- `description` - First 300 characters of description
- `tags` - Comma-separated list of video tags

**Example row:**
```
video_id,title,channel_name,channel_id,view_count,like_count,comment_count,published_at,video_url,duration,description,tags
dQw4w9WgXcQ,Claude AI Explained,Tech Channel,UCxxxxxx,50000,2500,180,2026-03-15T10:30:00Z,https://www.youtube.com/watch?v=dQw4w9WgXcQ,PT10M30S,"Claude is an AI assistant made by Anthropic...",Claude,AI,Review
```

### `youtube_summary.json`
Summary statistics and insights in JSON format.

**Structure:**
```json
{
  "metadata": {
    "collection_date": "2026-04-04T14:47:32.123456",
    "total_videos": 387,
    "total_views": 5230000,
    "date_range": {
      "earliest": "2024-03-01T...",
      "latest": "2026-04-03T..."
    }
  },
  "quota_usage": {
    "used": 8945,
    "limit": 10000,
    "percent": "89.5%"
  },
  "by_search_query": {
    "Claude AI": 50,
    "Claude vs ChatGPT": 48,
    ...
  },
  "top_20_videos": [
    {
      "video_id": "dQw4w9WgXcQ",
      "title": "Claude AI Explained",
      "channel": "Tech Channel",
      "views": 50000,
      "likes": 2500,
      "published": "2026-03-15T10:30:00Z",
      "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    },
    ...
  ],
  "top_10_channels": [
    {
      "channel_id": "UCxxxxxx",
      "channel_name": "Tech Channel",
      "video_count": 5
    },
    ...
  ]
}
```

## Search Queries

The scraper searches for these 8 queries:
1. `Claude AI`
2. `Claude vs ChatGPT`
3. `Claude Code`
4. `Anthropic Claude`
5. `Claude AI review`
6. `Claude Sonnet`
7. `Claude coding`
8. `#QuitGPT Claude`

Results are deduplicated by video_id, so the same video appearing in multiple search results is counted only once.

## How It Works

1. **Search Phase**: For each query, searches YouTube API and collects video IDs
2. **Details Phase**: Batches video IDs (max 50 per request) and fetches detailed statistics
3. **Deduplication**: Tracks collected video IDs to avoid duplicates across queries
4. **Quota Tracking**: Monitors API quota usage and stops gracefully before hitting 10,000 unit limit
5. **Output**: Exports clean CSV (sorted by views) and summary JSON

## Quota Management

The YouTube Data API v3 free tier provides **10,000 quota units per day**:
- Each `search().list()` call: **100 units**
- Each `videos().list()` call: **1 unit per video**

This scraper typically uses:
- 800 units for 8 search queries (100 × 8)
- ~9,000 units for fetching details on 300-500 videos
- **Total: ~9,800 units** (well under the 10,000 limit)

Quota resets daily at midnight Pacific Time.

## Handling Issues

### "quotaExceeded" Error
- Your daily quota is exhausted
- Quota resets at midnight PT
- Re-run the scraper tomorrow
- Consider reducing `limit_per_query` from 100 to 50 to use less quota

### Missing API Key
```
ERROR: YOUTUBE_API_KEY environment variable not set
Set your API key with: export YOUTUBE_API_KEY='your-key-here'
```

### Fewer Than 300 Videos
- Run again with a fresh API quota (next day)
- Modify `limit_per_query` parameter in `main()` if you have extra quota
- Add more search queries to `SEARCH_QUERIES` list

### API Connection Errors
- Check internet connection
- Verify API key is valid
- Ensure YouTube Data API v3 is enabled in Google Cloud

## Data Privacy & Ethics

- **Public Data Only**: All data collected is publicly available on YouTube
- **No Authentication Bypass**: Uses official YouTube API
- **Terms of Service**: Complies with YouTube API ToS
- **Rate Limiting**: Respects API quotas and includes delays between requests
- **Research Use**: Intended for legitimate research and educational purposes

## Development & Customization

### Add More Queries
Edit `SEARCH_QUERIES` list in `youtube_scraper.py`:
```python
SEARCH_QUERIES = [
    "Claude AI",
    "Your custom query here",
    ...
]
```

### Change Results Per Query
Modify the `limit_per_query` parameter:
```python
scraper.run(limit_per_query=200)  # Request 200 videos per query instead of 100
```

### Export to Different Format
The `self.videos` dictionary is available in memory. Add methods to `YouTubeScraper` class:
```python
def save_json(self, filename='videos.json'):
    with open(filename, 'w') as f:
        json.dump(self.videos, f, indent=2)
```

## Requirements.txt

```
google-api-python-client>=2.86.0
```

## License & Attribution

This scraper is built for educational and hackathon purposes. Use publicly available data responsibly.

## Support

**Common issues?**
- Check that `YOUTUBE_API_KEY` is set correctly
- Ensure you have ~15 minutes and at least 9,800 quota units available
- Check internet connection
- Review API error messages in the log output

For API key issues, see the [Google Cloud Documentation](https://cloud.google.com/docs/authentication/api-keys).
