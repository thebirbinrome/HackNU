"""
Reddit Claude AI — Scraper + Analysis Pipeline
=================================================
Hackathon project: Reverse-engineer Claude AI's viral growth playbook.
Single script: scrapes Reddit public data, then generates analysis charts + insights.

Usage:
    python reddit_scraper.py              # scrape + analyze
    python reddit_scraper.py --scrape     # scrape only
    python reddit_scraper.py --analyze    # analyze only (uses existing CSV)

Strategy:
  - No API key, no PRAW, no auth — pure public JSON endpoints
  - Scrapes top posts (all-time, year, month) + search results per subreddit
  - Handles pagination, rate limits (exponential back-off), resume on restart
  - Produces CSV + summary JSON + 5 PNG charts + terminal insights

Known Issues / Edge Cases:
  1. Reddit's public JSON API silently caps at ~1000 posts per listing endpoint.
     Workaround: combine top (alltime/year/month) + search to maximise coverage.
  2. Deleted/removed posts return "[deleted]" or "[removed]" for author/selftext.
     Workaround: stored as-is; downstream analysis should filter these.
  3. Reddit's search sometimes returns duplicates across different queries.
     Workaround: global deduplication dict keyed on post ID.
  4. The `after` pagination token occasionally returns an empty listing.
     Workaround: treat empty-children response as end-of-page, move on.
  5. Rate limiting: Reddit returns HTTP 429 or 503 under heavy load.
     Workaround: exponential back-off retry (up to 3 attempts, 2^n * 1s delay).
  6. Some posts have flair=None. Stored as empty string.
  7. Search endpoint caps results at ~250 per query even with pagination.
     Workaround: vary sort (relevance + new) to broaden coverage.
  8. `created_utc` is a float from Reddit; converted to ISO-8601 UTC string.
"""

import csv
import json
import logging
import re
import string
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests

# ===========================================================================
# CONFIGURATION
# ===========================================================================

SUBREDDITS = [
    "ClaudeAI",
    "ChatGPT",
    "artificial",
    "LocalLLaMA",
    "singularity",
]

SEARCH_QUERIES = [
    "Claude",
    "Claude AI",
    "Claude vs ChatGPT",
    "Claude Code",
    "Anthropic",
    "#QuitGPT",
]

TOP_TIME_FILTERS = ["all", "year", "month"]

SCRIPT_DIR = Path(__file__).parent
OUTPUT_CSV = SCRIPT_DIR / "reddit_claude_data.csv"
OUTPUT_JSON = SCRIPT_DIR / "reddit_summary.json"
CHARTS_DIR = SCRIPT_DIR / "charts"

REQUEST_DELAY = 5.0
MAX_RETRIES = 3
MAX_PAGES_PER_LISTING = 10
MAX_PAGES_SEARCH = 10

HEADERS = {
    "User-Agent": "hackathon-research-scraper/1.0 (public data only; contact: research@example.com)"
}

CSV_FIELDS = [
    "id", "subreddit", "title", "score", "num_comments",
    "created_utc", "author", "url", "selftext", "flair",
    "upvote_ratio", "permalink", "source_query",
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
    actually already someone anyone something
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

def _get(url: str, params: dict = None) -> Optional[dict]:
    """GET with retry + exponential back-off."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            time.sleep(REQUEST_DELAY)
            resp = requests.get(url, headers=HEADERS, params=params, timeout=15)
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code in (429, 503):
                wait = 2 ** attempt
                log.warning("Rate limited (HTTP %s). Waiting %ds (retry %d/%d).",
                            resp.status_code, wait, attempt, MAX_RETRIES)
                time.sleep(wait)
                continue
            if resp.status_code == 404:
                log.warning("404 Not Found: %s", url)
                return None
            log.warning("HTTP %s for %s (attempt %d/%d)",
                        resp.status_code, url, attempt, MAX_RETRIES)
        except requests.exceptions.RequestException as exc:
            wait = 2 ** attempt
            log.warning("Request error: %s. Waiting %ds (attempt %d/%d).",
                        exc, wait, attempt, MAX_RETRIES)
            time.sleep(wait)
    log.error("Giving up on %s after %d attempts.", url, MAX_RETRIES)
    return None


def _parse_post(child: dict, source_query: str = "") -> Optional[dict]:
    """Extract fields from a single Reddit post child object."""
    try:
        d = child.get("data", {})
        post_id = d.get("id")
        if not post_id:
            return None
        created_raw = d.get("created_utc", 0)
        created_dt = datetime.fromtimestamp(float(created_raw), tz=timezone.utc)
        created_str = created_dt.strftime("%Y-%m-%d %H:%M:%S UTC")
        selftext = (d.get("selftext") or "").strip()
        if selftext not in ("[removed]", "[deleted]"):
            selftext = selftext[:500]
        return {
            "id": post_id,
            "subreddit": d.get("subreddit", ""),
            "title": (d.get("title") or "").strip(),
            "score": d.get("score", 0),
            "num_comments": d.get("num_comments", 0),
            "created_utc": created_str,
            "author": d.get("author", "[deleted]"),
            "url": d.get("url", ""),
            "selftext": selftext,
            "flair": (d.get("link_flair_text") or "").strip(),
            "upvote_ratio": d.get("upvote_ratio", 0.0),
            "permalink": "https://www.reddit.com" + (d.get("permalink") or ""),
            "source_query": source_query,
        }
    except Exception as exc:
        log.debug("Error parsing post: %s", exc)
        return None


def _paginate(base_url: str, params: dict, max_pages: int, source: str, seen: dict) -> list:
    """Generic paginator for Reddit listing endpoints."""
    collected = []
    after = None
    for page in range(1, max_pages + 1):
        req_params = {**params}
        if after:
            req_params["after"] = after
        data = _get(base_url, params=req_params)
        if not data:
            break
        children = data.get("data", {}).get("children", [])
        if not children:
            break
        for child in children:
            post = _parse_post(child, source_query=source)
            if post and post["id"] not in seen:
                seen[post["id"]] = True
                collected.append(post)
        after = data.get("data", {}).get("after")
        if not after:
            break
    return collected


def _load_existing_csv() -> tuple:
    """Load previously scraped posts from CSV to enable resume on restart."""
    seen = {}
    existing = []
    try:
        with open(OUTPUT_CSV, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                pid = row.get("id")
                if pid and pid not in seen:
                    seen[pid] = True
                    existing.append(row)
        log.info("Resumed: loaded %d existing posts from CSV.", len(existing))
    except FileNotFoundError:
        log.info("No existing CSV — starting fresh.")
    return seen, existing


def run_scraper():
    """Phase 1: top posts, Phase 2: search queries. Writes CSV + summary JSON."""
    seen, all_posts = _load_existing_csv()

    log.info("=" * 60)
    log.info("SCRAPER — targeting %s", ", ".join(f"r/{s}" for s in SUBREDDITS))
    if all_posts:
        log.info("Resuming with %d posts already collected", len(all_posts))
    log.info("=" * 60)

    # Phase 1 — Top posts
    log.info("\n[Phase 1] Top posts across time filters...")
    for sub in SUBREDDITS:
        for tf in TOP_TIME_FILTERS:
            log.info("  r/%s top [%s]...", sub, tf)
            url = f"https://www.reddit.com/r/{sub}/top.json"
            posts = _paginate(url, {"t": tf, "limit": 25}, MAX_PAGES_PER_LISTING,
                              f"top:{tf}", seen)
            all_posts.extend(posts)
            log.info("    -> %d new (total: %d)", len(posts), len(all_posts))

    # Phase 2 — Search
    log.info("\n[Phase 2] Search queries...")
    for sub in SUBREDDITS:
        for query in SEARCH_QUERIES:
            log.info("  r/%s search '%s'...", sub, query)
            url = f"https://www.reddit.com/r/{sub}/search.json"
            for sort in ("relevance", "new"):
                posts = _paginate(url,
                                  {"q": query, "sort": sort, "restrict_sr": "true", "limit": 25},
                                  MAX_PAGES_SEARCH, f"search:{query}", seen)
                all_posts.extend(posts)
                log.info("    sort=%s -> %d new (total: %d)", sort, len(posts), len(all_posts))

    log.info("\nScraping done: %d unique posts.", len(all_posts))

    # Write CSV
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(all_posts)
    log.info("Wrote %s (%d rows)", OUTPUT_CSV.name, len(all_posts))

    # Write summary JSON
    by_sub = {}
    dates = []
    for p in all_posts:
        by_sub[p["subreddit"]] = by_sub.get(p["subreddit"], 0) + 1
        dates.append(p["created_utc"])
    dates_sorted = sorted(dates)
    top10 = sorted(all_posts, key=lambda p: int(p.get("score", 0)), reverse=True)[:10]

    summary = {
        "total_posts": len(all_posts),
        "by_subreddit": by_sub,
        "date_range": {
            "earliest": dates_sorted[0] if dates_sorted else None,
            "latest": dates_sorted[-1] if dates_sorted else None,
        },
        "top_10_posts_by_score": [
            {"title": p["title"], "subreddit": p["subreddit"],
             "score": p["score"], "url": p["permalink"], "date": p["created_utc"]}
            for p in top10
        ],
        "scrape_timestamp": datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
    }
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    log.info("Wrote %s", OUTPUT_JSON.name)

    # Print summary
    log.info("\n" + "=" * 60)
    log.info("SCRAPE SUMMARY")
    log.info("Total: %d posts | Range: %s → %s",
             len(all_posts), summary["date_range"]["earliest"], summary["date_range"]["latest"])
    for sr, c in sorted(by_sub.items(), key=lambda x: -x[1]):
        log.info("  r/%-20s %d", sr, c)
    log.info("=" * 60)


# ===========================================================================
# PART 2 — ANALYSIS
# ===========================================================================

def _load_for_analysis():
    """Load CSV into pandas DataFrame."""
    import pandas as pd
    print(f"\nLoading {OUTPUT_CSV.name} for analysis...")
    df = pd.read_csv(OUTPUT_CSV, dtype={"id": str})
    df["created_utc"] = pd.to_datetime(df["created_utc"], format="%Y-%m-%d %H:%M:%S UTC", utc=True)
    for col in ("score", "num_comments", "upvote_ratio"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["score"] = df["score"].fillna(0).astype(int)
    df["num_comments"] = df["num_comments"].fillna(0).astype(int)
    df["upvote_ratio"] = df["upvote_ratio"].fillna(0.5)
    df["title"] = df["title"].fillna("")
    df["selftext"] = df["selftext"].fillna("")
    df["flair"] = df["flair"].fillna("")
    df["author"] = df["author"].fillna("[deleted]")
    df["subreddit"] = df["subreddit"].fillna("unknown")
    df["month"] = df["created_utc"].dt.to_period("M")
    df = df.drop_duplicates(subset="id", keep="first")
    print(f"  {len(df):,} unique posts | {df['subreddit'].nunique()} subreddits | "
          f"{df['created_utc'].min():%Y-%m-%d} → {df['created_utc'].max():%Y-%m-%d}")
    return df


def _tokenize(text: str) -> list:
    """Lowercase, strip punctuation, remove stop words."""
    text = re.sub(r"https?://\S+", "", text.lower())
    text = text.translate(str.maketrans("", "", string.punctuation))
    return [t for t in text.split() if t not in STOP_WORDS and len(t) > 1]


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

    # --- Chart 1: Monthly Post Count ---
    monthly = df.groupby("month").size().reset_index(name="posts")
    monthly["month_str"] = monthly["month"].astype(str)

    fig, ax = plt.subplots(figsize=(14, 5))
    ax.bar(monthly["month_str"], monthly["posts"],
           color=sns.color_palette("viridis", len(monthly)))
    ax.set_xlabel("Month")
    ax.set_ylabel("Number of Posts")
    ax.set_title("Monthly Post Count — Claude AI Discourse on Reddit", fontweight="bold")
    plt.xticks(rotation=45, ha="right")
    peak = monthly["posts"].idxmax()
    ax.annotate(f'{monthly.loc[peak, "posts"]:,}',
                xy=(peak, monthly.loc[peak, "posts"]),
                ha="center", va="bottom", fontweight="bold", color="#d62728")
    fig.savefig(CHARTS_DIR / "01_monthly_post_count.png")
    plt.close(fig)
    print(f"  Saved: charts/01_monthly_post_count.png")

    # --- Chart 2: Monthly Engagement (score + volume) ---
    me = df.groupby("month").agg(
        total_score=("score", "sum"), post_count=("id", "count")
    ).reset_index()
    me["month_dt"] = me["month"].dt.to_timestamp()

    fig, ax1 = plt.subplots(figsize=(14, 5))
    ax1.fill_between(me["month_dt"], me["total_score"], alpha=0.3, color="#1f77b4")
    ax1.plot(me["month_dt"], me["total_score"], marker="o", color="#1f77b4", linewidth=2,
             label="Total Score")
    ax1.set_xlabel("Month")
    ax1.set_ylabel("Total Score", color="#1f77b4")
    ax1.tick_params(axis="y", labelcolor="#1f77b4")
    ax1.yaxis.set_major_formatter(ticker.FuncFormatter(lambda x, _: f"{x/1000:.0f}K"))
    ax2 = ax1.twinx()
    ax2.bar(me["month_dt"], me["post_count"], alpha=0.2, color="#ff7f0e", width=20, label="Posts")
    ax2.set_ylabel("Post Count", color="#ff7f0e")
    ax2.tick_params(axis="y", labelcolor="#ff7f0e")
    ax1.set_title("Monthly Engagement — Total Score & Post Volume", fontweight="bold")
    fig.legend(loc="upper left", bbox_to_anchor=(0.12, 0.92))
    fig.savefig(CHARTS_DIR / "02_monthly_engagement.png")
    plt.close(fig)
    print(f"  Saved: charts/02_monthly_engagement.png")

    # --- Chart 3: Top 10 Subreddits by Total Score ---
    top_subs = df.groupby("subreddit")["score"].sum().sort_values(ascending=True).tail(10)
    fig, ax = plt.subplots(figsize=(10, 6))
    colors = sns.color_palette("viridis", len(top_subs))
    bars = ax.barh(top_subs.index, top_subs.values, color=colors)
    for bar, val in zip(bars, top_subs.values):
        ax.text(val + top_subs.max() * 0.01, bar.get_y() + bar.get_height() / 2,
                f"{val:,}", va="center", fontsize=9)
    ax.set_xlabel("Total Score (Sum of Upvotes)")
    ax.set_title("Top 10 Subreddits by Total Score", fontweight="bold")
    ax.xaxis.set_major_formatter(ticker.FuncFormatter(lambda x, _: f"{x/1000:.0f}K"))
    fig.savefig(CHARTS_DIR / "03_top_subreddits_by_score.png")
    plt.close(fig)
    print(f"  Saved: charts/03_top_subreddits_by_score.png")

    # --- Chart 4: Engagement vs Controversy scatter ---
    plot_df = df if len(df) < 5000 else df.sample(5000, random_state=42)
    fig, ax = plt.subplots(figsize=(10, 7))
    sc = ax.scatter(plot_df["upvote_ratio"], plot_df["num_comments"],
                    c=plot_df["score"], cmap="viridis", alpha=0.5, s=15, edgecolors="none")
    fig.colorbar(sc, ax=ax, label="Score")
    ax.set_xlabel("Upvote Ratio (1.0 = unanimous)")
    ax.set_ylabel("Number of Comments")
    ax.set_title("Engagement vs Controversy — Do Divisive Posts Get More Comments?",
                 fontweight="bold")
    ax.set_yscale("symlog", linthresh=10)
    fig.savefig(CHARTS_DIR / "04_engagement_vs_controversy.png")
    plt.close(fig)
    print(f"  Saved: charts/04_engagement_vs_controversy.png")

    # --- Chart 5: Title Word Frequency — Top 100 vs Rest ---
    df_sorted = df.sort_values("score", ascending=False)
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
    ax1.set_title("Top 100 Posts (by score)\nMost Frequent Title Words", fontweight="bold")
    ax1.set_xlabel("Frequency")
    if rw20:
        w, c = zip(*rw20)
        ax2.barh(list(reversed(w)), list(reversed(c)), color=sns.color_palette("mako", 20))
    ax2.set_title("Remaining Posts\nMost Frequent Title Words", fontweight="bold")
    ax2.set_xlabel("Frequency")
    fig.suptitle("Title Word Frequency — Viral vs Regular Posts",
                 fontsize=14, fontweight="bold", y=1.02)
    fig.tight_layout()
    fig.savefig(CHARTS_DIR / "05_title_word_comparison.png")
    plt.close(fig)
    print(f"  Saved: charts/05_title_word_comparison.png")

    # -----------------------------------------------------------------------
    # Terminal Insights
    # -----------------------------------------------------------------------
    sep = "=" * 60
    print(f"\n{sep}")
    print("  INSIGHTS")
    print(sep)

    # 1. Viral density
    md = df.groupby("month").agg(total_score=("score", "sum"), posts=("id", "count"))
    md["viral_density"] = md["total_score"] / md["posts"]
    pm = md["viral_density"].idxmax()
    print(f"\n1. VIRAL DENSITY (highest avg score/post)")
    print(f"   Peak: {pm}  ({md.loc[pm, 'viral_density']:,.0f} avg score, "
          f"{md.loc[pm, 'posts']} posts)")

    # 2. Most engaged subreddit
    se = (df.groupby("subreddit")
            .agg(avg_comments=("num_comments", "mean"), posts=("id", "count"))
            .query("posts >= 10")
            .sort_values("avg_comments", ascending=False))
    print(f"\n2. MOST ENGAGED SUBREDDIT (avg comments/post, min 10 posts)")
    for sr, row in se.head(5).iterrows():
        print(f"   r/{sr:<20s} {row['avg_comments']:6.1f} avg comments  ({int(row['posts']):,} posts)")

    # 3. Controversy correlation
    corr = df["upvote_ratio"].corr(df["num_comments"])
    print(f"\n3. CONTROVERSY CORRELATION")
    print(f"   Pearson r(upvote_ratio, num_comments) = {corr:.4f}")
    if corr < -0.05:
        print(f"   → Controversial posts (lower ratio) DO get more comments.")
    elif corr > 0.05:
        print(f"   → Well-liked posts also attract more comments.")
    else:
        print(f"   → Weak/no linear correlation between controversy and comment volume.")

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
        print(f"   {word:<20s} {ratio:.1f}x more frequent in viral posts")

    # 5. Overview
    print(f"\n5. DATASET OVERVIEW")
    print(f"   Posts:    {len(df):,}")
    print(f"   Authors:  {df['author'].nunique():,}")
    print(f"   Median score: {df['score'].median():.0f}  |  Mean: {df['score'].mean():.0f}")
    print(f"   Total upvotes: {df['score'].sum():,}")
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
            # Default: scrape then analyze
            run_scraper()
            run_analysis()
    except KeyboardInterrupt:
        log.info("\nInterrupted by user.")
        sys.exit(0)
