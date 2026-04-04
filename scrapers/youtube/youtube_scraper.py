#!/usr/bin/env python3
"""
YouTube Scraper for Claude AI Content Analysis
Collects public data about Claude AI-related videos for hackathon project.
Uses YouTube Data API v3 (free tier - 10,000 quota units/day)
"""

import os
import json
import csv
import logging
from datetime import datetime
from collections import defaultdict
from typing import Dict, List, Set, Optional
import time

try:
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
except ImportError:
    print("ERROR: google-api-python-client not installed.")
    print("Install with: pip install google-api-python-client")
    exit(1)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
SEARCH_QUERIES = [
    "Claude AI",
    "Claude vs ChatGPT",
    "Claude Code",
    "Anthropic Claude",
    "Claude AI review",
    "Claude Sonnet",
    "Claude coding",
    "#QuitGPT Claude"
]

QUOTA_LIMIT = 10000
RESULTS_PER_PAGE = 50  # YouTube API max is 50

class QuotaTracker:
    """Track YouTube API quota usage"""
    def __init__(self, limit: int = QUOTA_LIMIT):
        self.limit = limit
        self.used = 0
        self.search_quota = 100  # Each search costs 100 units
        self.video_details_quota = 1  # Each video details call costs 1 unit

    def can_search(self) -> bool:
        return self.used + self.search_quota <= self.limit

    def can_get_details(self, count: int = 1) -> bool:
        return self.used + (count * self.video_details_quota) <= self.limit

    def add_search(self):
        self.used += self.search_quota
        logger.info(f"Quota: {self.used}/{self.limit} ({self.used*100//self.limit}%)")

    def add_details(self, count: int = 1):
        self.used += count * self.video_details_quota

    def remaining(self) -> int:
        return self.limit - self.used

    def percent_used(self) -> float:
        return (self.used / self.limit) * 100


class YouTubeScraper:
    """Main scraper for YouTube Claude AI content"""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.youtube = build('youtube', 'v3', developerKey=api_key)
        self.quota = QuotaTracker()

        # Data storage
        self.videos: Dict[str, Dict] = {}  # video_id -> data
        self.query_results: Dict[str, int] = {}  # query -> count
        self.channels: Dict[str, int] = defaultdict(int)  # channel_id -> count

        self.start_time = datetime.now()
        logger.info("YouTube Scraper initialized")

    def search_videos(self, query: str, max_results: int = 50) -> List[str]:
        """
        Search for videos matching query
        Returns list of video IDs
        """
        logger.info(f"Searching for: '{query}'")

        video_ids = []
        page_token = None
        pages_fetched = 0

        try:
            while len(video_ids) < max_results and self.quota.can_search():
                logger.info(f"  Fetching page {pages_fetched + 1}... (quota: {self.quota.remaining()} remaining)")

                request = self.youtube.search().list(
                    q=query,
                    part='id',
                    type='video',
                    maxResults=RESULTS_PER_PAGE,
                    pageToken=page_token,
                    relevanceLanguage='en',
                    order='relevance'
                )

                response = request.execute()
                self.quota.add_search()

                # Extract video IDs
                for item in response.get('items', []):
                    if item['id']['kind'] == 'youtube#video':
                        video_id = item['id']['videoId']
                        if video_id not in self.videos:
                            video_ids.append(video_id)

                page_token = response.get('nextPageToken')
                pages_fetched += 1

                if not page_token or len(video_ids) >= max_results:
                    break

                # Rate limiting
                time.sleep(0.1)

        except HttpError as e:
            logger.error(f"API Error during search: {e}")
            if 'quotaExceeded' in str(e):
                logger.error("Quota exceeded! Stopping search.")
                return video_ids

        logger.info(f"  Found {len(video_ids)} new videos for '{query}'")
        self.query_results[query] = len(video_ids)
        return video_ids

    def get_video_details(self, video_ids: List[str]) -> None:
        """
        Fetch detailed information for videos
        Can handle up to 50 videos per request
        """
        if not video_ids:
            return

        logger.info(f"Fetching details for {len(video_ids)} videos...")

        # Process in batches of 50 (YouTube API limit)
        batch_size = 50
        for i in range(0, len(video_ids), batch_size):
            if not self.quota.can_get_details(min(batch_size, len(video_ids) - i)):
                logger.warning("Quota limit approaching, stopping detail fetches")
                break

            batch = video_ids[i:i + batch_size]

            try:
                request = self.youtube.videos().list(
                    part='snippet,statistics,contentDetails',
                    id=','.join(batch)
                )

                response = request.execute()
                self.quota.add_details(len(batch))

                for item in response.get('items', []):
                    video_id = item['id']
                    if video_id not in self.videos:
                        self._process_video_item(item)

                time.sleep(0.1)

            except HttpError as e:
                logger.error(f"API Error fetching details: {e}")
                if 'quotaExceeded' in str(e):
                    logger.error("Quota exceeded! Stopping detail fetches.")
                    break

    def _process_video_item(self, item: Dict) -> None:
        """Extract and store video data"""
        try:
            video_id = item['id']
            snippet = item.get('snippet', {})
            stats = item.get('statistics', {})
            details = item.get('contentDetails', {})

            data = {
                'video_id': video_id,
                'title': snippet.get('title', 'N/A'),
                'channel_name': snippet.get('channelTitle', 'N/A'),
                'channel_id': snippet.get('channelId', 'N/A'),
                'view_count': int(stats.get('viewCount', 0)),
                'like_count': int(stats.get('likeCount', 0)),
                'comment_count': int(stats.get('commentCount', 0)),
                'published_at': snippet.get('publishedAt', 'N/A'),
                'video_url': f'https://www.youtube.com/watch?v={video_id}',
                'duration': details.get('duration', 'N/A'),
                'description': (snippet.get('description', '')[:300] + '...') if snippet.get('description') else 'N/A',
                'tags': ', '.join(snippet.get('tags', []))
            }

            self.videos[video_id] = data
            self.channels[data['channel_id']] += 1

        except Exception as e:
            logger.warning(f"Error processing video {item.get('id', 'unknown')}: {e}")

    def run(self, limit_per_query: int = 100) -> None:
        """
        Main execution: search all queries and collect data
        """
        logger.info(f"Starting scrape for {len(SEARCH_QUERIES)} queries")
        logger.info(f"Quota limit: {self.quota.limit} units")

        for query in SEARCH_QUERIES:
            if not self.quota.can_search():
                logger.warning(f"Quota limit reached ({self.quota.percent_used():.1f}% used). Stopping searches.")
                break

            video_ids = self.search_videos(query, max_results=limit_per_query)

            if video_ids:
                self.get_video_details(video_ids)

        logger.info(f"Scrape complete. Collected {len(self.videos)} unique videos")
        logger.info(f"Quota used: {self.quota.used}/{self.quota.limit} ({self.quota.percent_used():.1f}%)")

    def save_csv(self, filename: str = 'youtube_claude_data.csv') -> None:
        """Export videos to CSV, sorted by view_count descending"""
        logger.info(f"Saving {len(self.videos)} videos to {filename}")

        # Sort by view_count descending
        sorted_videos = sorted(
            self.videos.values(),
            key=lambda x: x['view_count'],
            reverse=True
        )

        with open(filename, 'w', newline='', encoding='utf-8') as f:
            fieldnames = [
                'video_id', 'title', 'channel_name', 'channel_id',
                'view_count', 'like_count', 'comment_count',
                'published_at', 'video_url', 'duration',
                'description', 'tags'
            ]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(sorted_videos)

        logger.info(f"CSV saved: {filename}")

    def save_summary(self, filename: str = 'youtube_summary.json') -> None:
        """Export summary statistics as JSON"""
        logger.info(f"Saving summary to {filename}")

        # Top 20 videos by view_count
        top_videos = sorted(
            self.videos.values(),
            key=lambda x: x['view_count'],
            reverse=True
        )[:20]

        # Top 10 channels by frequency
        top_channels = sorted(
            self.channels.items(),
            key=lambda x: x[1],
            reverse=True
        )[:10]

        # Map channel_id to channel_name
        channel_names = {
            v['channel_id']: v['channel_name']
            for v in self.videos.values()
        }

        summary = {
            'metadata': {
                'collection_date': self.start_time.isoformat(),
                'total_videos': len(self.videos),
                'total_views': sum(v['view_count'] for v in self.videos.values()),
                'date_range': {
                    'earliest': min((v['published_at'] for v in self.videos.values()), default='N/A'),
                    'latest': max((v['published_at'] for v in self.videos.values()), default='N/A')
                }
            },
            'quota_usage': {
                'used': self.quota.used,
                'limit': self.quota.limit,
                'percent': f"{self.quota.percent_used():.1f}%"
            },
            'by_search_query': self.query_results,
            'top_20_videos': [
                {
                    'video_id': v['video_id'],
                    'title': v['title'],
                    'channel': v['channel_name'],
                    'views': v['view_count'],
                    'likes': v['like_count'],
                    'published': v['published_at'],
                    'url': v['video_url']
                }
                for v in top_videos
            ],
            'top_10_channels': [
                {
                    'channel_id': cid,
                    'channel_name': channel_names.get(cid, 'Unknown'),
                    'video_count': count
                }
                for cid, count in top_channels
            ]
        }

        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)

        logger.info(f"Summary saved: {filename}")


def main():
    """Main entry point"""
    api_key = os.getenv('YOUTUBE_API_KEY')

    if not api_key:
        logger.error("ERROR: YOUTUBE_API_KEY environment variable not set")
        logger.error("Set your API key with: export YOUTUBE_API_KEY='your-key-here'")
        exit(1)

    scraper = YouTubeScraper(api_key)
    scraper.run(limit_per_query=100)

    scraper.save_csv('youtube_claude_data.csv')
    scraper.save_summary('youtube_summary.json')

    logger.info("All done!")


if __name__ == '__main__':
    main()
