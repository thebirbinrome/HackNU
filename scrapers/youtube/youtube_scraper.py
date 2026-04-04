"""
YouTube Claude AI — Scraper + Analysis Pipeline
==================================================
Hackathon project: Reverse-engineer Claude AI's viral growth playbook.
Single script: scrapes YouTube public data via Data API v3, then generates
analysis charts + insights.

Usage:
    python youtube_scraper.py                # scrape + analyze
    python youtube_scraper.py --scrape       # scrape only
    python youtube_scraper.py --analyze      # analyze only (uses existing CSV)

Strategy:
  - Uses YouTube Data API v3 (free tier, 10,000 quota units/day)
  - Searches 8 queries, fetches video details in batches of 50
  - Deduplicates by video_id, resumes from existing CSV on restart
  - Produces CSV + summary JSON + 5 PNG charts + terminal insights

Known Issues / Edge Cases:
  1. YouTube API quota is 10,000 units/day. Each search costs 100 units,
     each video details batch costs 1 unit. Budget carefully.
  2. Some videos have disabled like/comment counts — stored as 0.
  3. Duration is ISO 8601 format (PT1H2M3S). Stored as-is for simplicity.
  4. Deleted/private videos may appear in search but fail on details fetch.
     Workaround: silently skip missing items in the details response.
  5. API key must be set via YOUTUBE_API_KEY environment variable.
  6. Search results are relevance-sorted; YouTube caps at ~500 results per query.
  7. Tags field may be absent on many videos. Stored as empty string.
  8. Resume: existing CSV is loaded on startup, seen video_ids are skipped.

Requirements:
    pip install google-api-python-client matplotlib seaborn pandas
"""

import csv
import json
import logging
import os
import re
import string
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ===========================================================================
# CONFIGURATION
# ===========================================================================

SEARCH_QUERIES = [
    "Claude AI",
    "Claude vs ChatGPT",
    "Claude Code",
    "Anthropic Claude",
    "Claude AI review",
    "Claude Sonnet",
    "Claude coding",
    "#QuitGPT Claude",
]

QUOTA_LIMIT = 10000
RESULTS_PER_PAGE = 50
LIMIT_PER_QUERY = 100

SCRIPT_DIR = Path(__file__).parent
OUTPUT_CSV = SCRIPT_DIR / "youtube_claude_data.csv"
OUTPUT_JSON = SCRIPT_DIR / "youtube_summary.json"
CHARTS_DIR = SCRIPT_DIR / "charts"

CSV_FIELDS = [
    "video_id", "title", "channel_name", "channel_id",
    "view_count", "like_count", "comment_count",
    "published_at", "video_url", "duration",
    "description", "tags",
]

STOP_WORDS = set("""
    a about above after again against all am an and any are arent as at be
    because been before being below between both but by can cant cannot could
    couldnt did didnt do does doesnt doing dont down during each few for from
    further get got had hadnt has hasnt have havent having he hed hell hes her
    here heres hers herself him himself his how hows i id ill im ive if in
    into is isnt it its itself just lets me more most mustnt my myself no nor
    not of off on once only or other ought our ours ourselves out over own
    really same shant she shed shell shes should shouldnt so some such than
    that thats the their theirs them themselves then there theres these they
    theyd theyll theyre theyve this those through to too under until up upon
    very was wasnt we wed well were weve were werent what whats when whens
    where wheres which while who whos whom why whys will with wont would
    wouldnt you youd youll youre youve your yours yourself yourselves also
    like just even still one would could will much get got use using used new
    way going know think make thing people right want need something really
    actually already someone anyone something youtube video videos
""".split())

# ===========================================================================
# LOGGING
# ===========================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(SCRIPT_DIR / "scraper.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)


# ===========================================================================
# PART 1 — SCRAPER
# ===========================================================================

class QuotaTracker:
    """Track YouTube API quota usage."""
    SEARCH_COST = 100
    DETAILS_COST = 1

    def __init__(self, limit: int = QUOTA_LIMIT):
        self.limit = limit
        self.used = 0

    def can_search(self) -> bool:
        return self.used + self.SEARCH_COST <= self.limit

    def can_get_details(self, count: int = 1) -> bool:
        return self.used + (count * self.DETAILS_COST) <= self.limit

    def add_search(self):
        self.used += self.SEARCH_COST
        log.info("  Quota: %d/%d (%d%%)", self.used, self.limit, self.used * 100 // self.limit)

    def add_details(self, count: int = 1):
        self.used += count * self.DETAILS_COST

    def remaining(self) -> int:
        return self.limit - self.used


def _load_existing_csv() -> tuple:
    """Load previously scraped videos from CSV to enable resume on restart."""
    seen = {}
    existing = []
    try:
        with open(OUTPUT_CSV, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                vid = row.get("video_id")
                if vid and vid not in seen:
                    seen[vid] = True
                    existing.append(row)
        log.info("Resumed: loaded %d existing videos from CSV.", len(existing))
    except FileNotFoundError:
        log.info("No existing CSV — starting fresh.")
    return seen, existing


def _parse_video_item(item: dict) -> Optional[dict]:
    """Extract fields from a YouTube API video item."""
    try:
        video_id = item["id"]
        snippet = item.get("snippet", {})
        stats = item.get("statistics", {})
        details = item.get("contentDetails", {})
        desc = (snippet.get("description") or "")[:300]
        return {
            "video_id": video_id,
            "title": snippet.get("title", ""),
            "channel_name": snippet.get("channelTitle", ""),
            "channel_id": snippet.get("channelId", ""),
            "view_count": int(stats.get("viewCount", 0)),
            "like_count": int(stats.get("likeCount", 0)),
            "comment_count": int(stats.get("commentCount", 0)),
            "published_at": snippet.get("publishedAt", ""),
            "video_url": f"https://www.youtube.com/watch?v={video_id}",
            "duration": details.get("duration", ""),
            "description": desc,
            "tags": ", ".join(snippet.get("tags", [])),
        }
    except Exception as exc:
        log.debug("Error parsing video item: %s", exc)
        return None


def run_scraper():
    """Search YouTube for queries, fetch video details, write CSV + JSON."""
    try:
        from googleapiclient.discovery import build
        from googleapiclient.errors import HttpError
    except ImportError:
        log.error("google-api-python-client not installed. Run: pip install google-api-python-client")
        sys.exit(1)

    api_key = os.getenv("YOUTUBE_API_KEY")
    if not api_key:
        log.error("YOUTUBE_API_KEY environment variable not set.")
        log.error("Set it with: export YOUTUBE_API_KEY='your-key-here'")
        sys.exit(1)

    youtube = build("youtube", "v3", developerKey=api_key)
    quota = QuotaTracker()
    seen, all_videos = _load_existing_csv()
    channels = defaultdict(int)

    # Rebuild channel counts from existing data
    for v in all_videos:
        channels[v.get("channel_id", "")] += 1

    log.info("=" * 60)
    log.info("YOUTUBE SCRAPER — %d queries, quota limit %d", len(SEARCH_QUERIES), QUOTA_LIMIT)
    if all_videos:
        log.info("Resuming with %d videos already collected", len(all_videos))
    log.info("=" * 60)

    query_results = {}

    for query in SEARCH_QUERIES:
        if not quota.can_search():
            log.warning("Quota limit reached (%d/%d). Stopping.", quota.used, quota.limit)
            break

        log.info("\nSearching: '%s'...", query)
        video_ids = []
        page_token = None

        # Search phase — collect video IDs
        while len(video_ids) < LIMIT_PER_QUERY and quota.can_search():
            try:
                request = youtube.search().list(
                    q=query, part="id", type="video",
                    maxResults=RESULTS_PER_PAGE,
                    pageToken=page_token,
                    relevanceLanguage="en", order="relevance",
                )
                response = request.execute()
                quota.add_search()

                for item in response.get("items", []):
                    if item["id"]["kind"] == "youtube#video":
                        vid = item["id"]["videoId"]
                        if vid not in seen:
                            video_ids.append(vid)

                page_token = response.get("nextPageToken")
                if not page_token or len(video_ids) >= LIMIT_PER_QUERY:
                    break
                time.sleep(0.1)

            except HttpError as e:
                if "quotaExceeded" in str(e):
                    log.error("Quota exceeded during search. Stopping.")
                    break
                log.warning("API error during search: %s", e)
                break

        log.info("  Found %d new video IDs for '%s'", len(video_ids), query)
        query_results[query] = len(video_ids)

        # Details phase — fetch metadata in batches of 50
        for i in range(0, len(video_ids), 50):
            batch = video_ids[i:i + 50]
            if not quota.can_get_details(len(batch)):
                log.warning("Quota limit approaching. Stopping detail fetches.")
                break
            try:
                request = youtube.videos().list(
                    part="snippet,statistics,contentDetails",
                    id=",".join(batch),
                )
                response = request.execute()
                quota.add_details(len(batch))

                for item in response.get("items", []):
                    video = _parse_video_item(item)
                    if video and video["video_id"] not in seen:
                        seen[video["video_id"]] = True
                        all_videos.append(video)
                        channels[video["channel_id"]] += 1

                time.sleep(0.1)
            except HttpError as e:
                if "quotaExceeded" in str(e):
                    log.error("Quota exceeded during details fetch. Stopping.")
                    break
                log.warning("API error fetching details: %s", e)

        log.info("  Running total: %d unique videos", len(all_videos))

    log.info("\nScraping done: %d unique videos. Quota used: %d/%d",
             len(all_videos), quota.used, quota.limit)

    # Write CSV (sorted by view_count descending)
    all_videos_sorted = sorted(all_videos,
                               key=lambda v: int(v.get("view_count", 0)), reverse=True)
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(all_videos_sorted)
    log.info("Wrote %s (%d rows)", OUTPUT_CSV.name, len(all_videos_sorted))

    # Write summary JSON
    channel_names = {v.get("channel_id", ""): v.get("channel_name", "")
                     for v in all_videos}
    top_channels = sorted(channels.items(), key=lambda x: x[1], reverse=True)[:10]
    dates = [v["published_at"] for v in all_videos if v.get("published_at")]
    top20 = all_videos_sorted[:20]

    summary = {
        "total_videos": len(all_videos),
        "total_views": sum(int(v.get("view_count", 0)) for v in all_videos),
        "date_range": {
            "earliest": min(dates) if dates else None,
            "latest": max(dates) if dates else None,
        },
        "quota_usage": {"used": quota.used, "limit": quota.limit},
        "by_search_query": query_results,
        "top_20_videos": [
            {"title": v["title"], "channel": v["channel_name"],
             "views": v["view_count"], "url": v["video_url"], "date": v["published_at"]}
            for v in top20
        ],
        "top_10_channels": [
            {"channel_id": cid, "channel_name": channel_names.get(cid, ""),
             "video_count": cnt}
            for cid, cnt in top_channels
        ],
        "scrape_timestamp": datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
    }
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    log.info("Wrote %s", OUTPUT_JSON.name)

    # Print summary
    log.info("\n" + "=" * 60)
    log.info("SCRAPE SUMMARY")
    log.info("Total: %d videos | Views: %s | Range: %s → %s",
             summary["total_videos"], f"{summary['total_views']:,}",
             summary["date_range"]["earliest"], summary["date_range"]["latest"])
    for cid, cnt in top_channels[:5]:
        log.info("  %-30s %d videos", channel_names.get(cid, cid)[:30], cnt)
    log.info("=" * 60)


# ===========================================================================
# PART 2 — ANALYSIS
# ===========================================================================

def _load_for_analysis():
    """Load CSV into pandas DataFrame."""
    import pandas as pd
    print(f"\nLoading {OUTPUT_CSV.name} for analysis...")
    df = pd.read_csv(OUTPUT_CSV, dtype={"video_id": str, "channel_id": str})
    df["published_at"] = pd.to_datetime(df["published_at"], errors="coerce")
    for col in ("view_count", "like_count", "comment_count"):
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
    df["title"] = df["title"].fillna("")
    df["channel_name"] = df["channel_name"].fillna("")
    df["description"] = df["description"].fillna("")
    df["tags"] = df["tags"].fillna("")
    df = df.dropna(subset=["published_at"])
    df["month"] = df["published_at"].dt.to_period("M")
    df["month_str"] = df["published_at"].dt.strftime("%Y-%m")
    df["engagement_rate"] = (df["like_count"] + df["comment_count"]) / (df["view_count"] + 1)
    df = df.drop_duplicates(subset="video_id", keep="first")
    print(f"  {len(df):,} unique videos | {df['channel_id'].nunique()} channels | "
          f"{df['published_at'].min():%Y-%m-%d} → {df['published_at'].max():%Y-%m-%d}")
    return df


def _tokenize(text: str) -> list:
    """Lowercase, strip punctuation, remove stop words."""
    text = re.sub(r"https?://\S+", "", text.lower())
    text = text.translate(str.maketrans("", "", string.punctuation))
    return [t for t in text.split() if t not in STOP_WORDS and len(t) > 2]


def run_analysis():
    """Generate 5 charts + print terminal insights."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.ticker as ticker
    import seaborn as sns
    import pandas as pd
    import numpy as np

    sns.set_theme(style="whitegrid", palette="viridis", font_scale=1.1)
    plt.rcParams["figure.dpi"] = 150
    plt.rcParams["savefig.bbox"] = "tight"
    CHARTS_DIR.mkdir(parents=True, exist_ok=True)

    df = _load_for_analysis()
    print("\nGenerating charts...")

    # --- Chart 1: Monthly Video Count ---
    monthly = df.groupby("month_str").size().reset_index(name="videos")

    fig, ax = plt.subplots(figsize=(14, 5))
    ax.bar(monthly["month_str"], monthly["videos"],
           color=sns.color_palette("viridis", len(monthly)))
    ax.set_xlabel("Month")
    ax.set_ylabel("Number of Videos")
    ax.set_title("Monthly Video Count — Claude AI Content on YouTube", fontweight="bold")
    plt.xticks(rotation=45, ha="right")
    peak = monthly["videos"].idxmax()
    ax.annotate(f'{monthly.loc[peak, "videos"]:,}',
                xy=(peak, monthly.loc[peak, "videos"]),
                ha="center", va="bottom", fontweight="bold", color="#d62728")
    fig.savefig(CHARTS_DIR / "01_monthly_video_count.png")
    plt.close(fig)
    print("  Saved: charts/01_monthly_video_count.png")

    # --- Chart 2: Monthly Views (engagement + volume) ---
    me = df.groupby("month").agg(
        total_views=("view_count", "sum"), video_count=("video_id", "count")
    ).reset_index()
    me["month_dt"] = me["month"].dt.to_timestamp()

    fig, ax1 = plt.subplots(figsize=(14, 5))
    ax1.fill_between(me["month_dt"], me["total_views"], alpha=0.3, color="#1f77b4")
    ax1.plot(me["month_dt"], me["total_views"], marker="o", color="#1f77b4", linewidth=2,
             label="Total Views")
    ax1.set_xlabel("Month")
    ax1.set_ylabel("Total Views", color="#1f77b4")
    ax1.tick_params(axis="y", labelcolor="#1f77b4")
    ax1.yaxis.set_major_formatter(ticker.FuncFormatter(
        lambda x, _: f"{x/1e6:.0f}M" if x >= 1e6 else f"{x/1e3:.0f}K"))
    ax2 = ax1.twinx()
    ax2.bar(me["month_dt"], me["video_count"], alpha=0.2, color="#ff7f0e", width=20, label="Videos")
    ax2.set_ylabel("Video Count", color="#ff7f0e")
    ax2.tick_params(axis="y", labelcolor="#ff7f0e")
    ax1.set_title("Monthly Engagement — Total Views & Video Volume", fontweight="bold")
    fig.legend(loc="upper left", bbox_to_anchor=(0.12, 0.92))
    fig.savefig(CHARTS_DIR / "02_monthly_views.png")
    plt.close(fig)
    print("  Saved: charts/02_monthly_views.png")

    # --- Chart 3: Top 10 Channels by Total Views ---
    ch_stats = df.groupby("channel_name").agg(
        total_views=("view_count", "sum"), video_count=("video_id", "count")
    )
    top_ch = ch_stats.nlargest(10, "total_views").sort_values("total_views", ascending=True)

    fig, ax = plt.subplots(figsize=(10, 6))
    colors = sns.color_palette("viridis", len(top_ch))
    bars = ax.barh(top_ch.index, top_ch["total_views"], color=colors)
    for bar, (_, row) in zip(bars, top_ch.iterrows()):
        views = row["total_views"]
        label = f"{views/1e6:.1f}M ({int(row['video_count'])} videos)" if views >= 1e6 \
            else f"{views/1e3:.0f}K ({int(row['video_count'])} videos)"
        ax.text(views + top_ch["total_views"].max() * 0.01,
                bar.get_y() + bar.get_height() / 2, label, va="center", fontsize=9)
    ax.set_xlabel("Total Views")
    ax.set_title("Top 10 Channels by Total Views", fontweight="bold")
    ax.xaxis.set_major_formatter(ticker.FuncFormatter(
        lambda x, _: f"{x/1e6:.0f}M" if x >= 1e6 else f"{x/1e3:.0f}K"))
    fig.savefig(CHARTS_DIR / "03_top_channels_by_views.png")
    plt.close(fig)
    print("  Saved: charts/03_top_channels_by_views.png")

    # --- Chart 4: Engagement Rate vs Channel Scale ---
    ch_scatter = df.groupby("channel_id").agg(
        total_views=("view_count", "sum"),
        avg_engagement=("engagement_rate", "mean"),
        channel_name=("channel_name", "first"),
    ).reset_index()
    ch_scatter = ch_scatter[ch_scatter["total_views"] > 0]
    ch_scatter["log_views"] = np.log10(ch_scatter["total_views"])

    fig, ax = plt.subplots(figsize=(10, 7))
    sc = ax.scatter(ch_scatter["log_views"], ch_scatter["avg_engagement"] * 100,
                    c=ch_scatter["total_views"], cmap="viridis", alpha=0.5, s=30,
                    edgecolors="none")
    fig.colorbar(sc, ax=ax, label="Total Views")
    ax.set_xlabel("log10(Total Channel Views)")
    ax.set_ylabel("Average Engagement Rate (%)")
    ax.set_title("Engagement Rate vs Channel Scale", fontweight="bold")
    fig.savefig(CHARTS_DIR / "04_engagement_vs_scale.png")
    plt.close(fig)
    print("  Saved: charts/04_engagement_vs_scale.png")

    # --- Chart 5: Title Word Frequency — Top 100 vs Rest ---
    df_sorted = df.sort_values("view_count", ascending=False)
    top100, rest = df_sorted.head(100), df_sorted.iloc[100:]

    top_words = Counter()
    rest_words = Counter()
    for t in top100["title"]:
        top_words.update(_tokenize(t))
    for t in rest["title"]:
        rest_words.update(_tokenize(t))

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 7))
    tw20 = top_words.most_common(20)
    rw20 = rest_words.most_common(20)
    if tw20:
        w, c = zip(*tw20)
        ax1.barh(list(reversed(w)), list(reversed(c)), color=sns.color_palette("rocket", 20))
    ax1.set_title("Top 100 Videos (by views)\nMost Frequent Title Words", fontweight="bold")
    ax1.set_xlabel("Frequency")
    if rw20:
        w, c = zip(*rw20)
        ax2.barh(list(reversed(w)), list(reversed(c)), color=sns.color_palette("mako", 20))
    ax2.set_title("Remaining Videos\nMost Frequent Title Words", fontweight="bold")
    ax2.set_xlabel("Frequency")
    fig.suptitle("Title Word Frequency — Viral vs Regular Videos",
                 fontsize=14, fontweight="bold", y=1.02)
    fig.tight_layout()
    fig.savefig(CHARTS_DIR / "05_title_word_comparison.png")
    plt.close(fig)
    print("  Saved: charts/05_title_word_comparison.png")

    # -----------------------------------------------------------------------
    # Terminal Insights
    # -----------------------------------------------------------------------
    sep = "=" * 60
    print(f"\n{sep}")
    print("  INSIGHTS")
    print(sep)

    # 1. Viral density — highest avg views/video per month
    md = df.groupby("month").agg(total_views=("view_count", "sum"), videos=("video_id", "count"))
    md["viral_density"] = md["total_views"] / md["videos"]
    pm = md["viral_density"].idxmax()
    print(f"\n1. VIRAL DENSITY (highest avg views/video)")
    print(f"   Peak: {pm}  ({md.loc[pm, 'viral_density']:,.0f} avg views, "
          f"{md.loc[pm, 'videos']} videos)")

    # 2. Most efficient channels (highest views with fewest videos, min 3)
    ch_eff = ch_stats[ch_stats["video_count"] >= 3].copy()
    ch_eff["efficiency"] = ch_eff["total_views"] / ch_eff["video_count"]
    ch_eff = ch_eff.sort_values("efficiency", ascending=False)
    print(f"\n2. MOST EFFICIENT CHANNELS (avg views/video, min 3 videos)")
    for ch, row in ch_eff.head(5).iterrows():
        print(f"   {ch:<30s} {row['efficiency']:>12,.0f} avg views  "
              f"({int(row['video_count'])} videos, {row['total_views']:,.0f} total)")

    # 3. Engagement metrics
    avg_eng = df["engagement_rate"].mean() * 100
    avg_like = (df["like_count"] / (df["view_count"] + 1)).mean() * 100
    avg_comment = (df["comment_count"] / (df["view_count"] + 1)).mean() * 100
    print(f"\n3. ENGAGEMENT METRICS")
    print(f"   Avg engagement rate: {avg_eng:.2f}%")
    print(f"   Avg like rate:       {avg_like:.2f}%")
    print(f"   Avg comment rate:    {avg_comment:.2f}%")

    # 4. Distinctive viral vocabulary
    total_t = sum(top_words.values()) or 1
    total_r = sum(rest_words.values()) or 1
    scored = {}
    for word in [w for w, _ in top_words.most_common(100)]:
        ft = top_words[word] / total_t
        fr = rest_words.get(word, 0) / total_r
        scored[word] = ft / fr if fr > 0 else ft * 1000
    distinctive = sorted(scored.items(), key=lambda x: -x[1])[:15]
    print(f"\n4. VIRAL VOCABULARY (words overrepresented in top 100)")
    for word, ratio in distinctive:
        print(f"   {word:<20s} {ratio:.1f}x more frequent in viral videos")

    # 5. Overview
    print(f"\n5. DATASET OVERVIEW")
    print(f"   Videos:       {len(df):,}")
    print(f"   Channels:     {df['channel_id'].nunique():,}")
    print(f"   Total views:  {df['view_count'].sum():,}")
    print(f"   Median views: {df['view_count'].median():,.0f}  |  Mean: {df['view_count'].mean():,.0f}")
    print(f"   Max views:    {df['view_count'].max():,}")
    print(sep)
    print(f"\nCharts saved to: {CHARTS_DIR.resolve()}")


# ===========================================================================
# ENTRY POINT
# ===========================================================================

if __name__ == "__main__":
    args = sys.argv[1:]

    scrape_only = "--scrape" in args
    analyze_only = "--analyze" in args

    try:
        if analyze_only:
            run_analysis()
        elif scrape_only:
            run_scraper()
        else:
            run_scraper()
            run_analysis()
    except KeyboardInterrupt:
        log.info("\nInterrupted by user.")
        sys.exit(0)
