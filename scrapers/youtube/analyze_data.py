#!/usr/bin/env python3
"""
YouTube Claude AI Content Analysis
Senior Data Science Analysis of collected YouTube data
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime
import logging
from collections import Counter
import re
import os

# NLP imports
try:
    from nltk.corpus import stopwords
    import nltk
    nltk.download('stopwords', quiet=True)
except ImportError:
    print("Installing NLTK...")
    os.system("pip3 install nltk")
    from nltk.corpus import stopwords
    import nltk
    nltk.download('stopwords', quiet=True)

# Setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Set style
sns.set_style("whitegrid")
plt.rcParams['figure.figsize'] = (12, 6)

# ============================================================================
# 1. DATA LOADING & CLEANING
# ============================================================================

def load_and_clean_data(filepath: str) -> pd.DataFrame:
    """Load CSV and perform data cleaning"""
    logger.info(f"Loading data from {filepath}")

    df = pd.read_csv(filepath)
    logger.info(f"Loaded {len(df)} videos")

    # Convert published_at to datetime
    df['published_at'] = pd.to_datetime(df['published_at'], errors='coerce')

    # Handle missing values
    df['like_count'] = pd.to_numeric(df['like_count'], errors='coerce').fillna(0)
    df['comment_count'] = pd.to_numeric(df['comment_count'], errors='coerce').fillna(0)
    df['view_count'] = pd.to_numeric(df['view_count'], errors='coerce').fillna(0)

    # Remove rows with missing critical data
    initial_count = len(df)
    df = df.dropna(subset=['published_at', 'view_count'])
    logger.info(f"After cleaning: {len(df)} videos (removed {initial_count - len(df)})")

    # Extract month and year for aggregations
    df['year_month'] = df['published_at'].dt.to_period('M')
    df['month_name'] = df['published_at'].dt.strftime('%Y-%m')

    # Calculate engagement metrics
    df['engagement_rate'] = (df['like_count'] + df['comment_count']) / (df['view_count'] + 1)
    df['like_rate'] = df['like_count'] / (df['view_count'] + 1)
    df['comment_rate'] = df['comment_count'] / (df['view_count'] + 1)

    return df


# ============================================================================
# 2. VISUALIZATION 1: MONTHLY VIDEO COUNT
# ============================================================================

def plot_monthly_video_count(df: pd.DataFrame) -> None:
    """Time-series bar chart: videos published per month"""
    logger.info("Creating monthly video count chart...")

    monthly_counts = df.groupby('month_name').size()

    fig, ax = plt.subplots(figsize=(14, 6))
    monthly_counts.plot(kind='bar', ax=ax, color='steelblue', edgecolor='black', alpha=0.7)

    ax.set_title('YouTube Claude Content: Videos Published Per Month', fontsize=14, fontweight='bold')
    ax.set_xlabel('Month', fontsize=12)
    ax.set_ylabel('Number of Videos', fontsize=12)
    ax.grid(axis='y', alpha=0.3)
    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()

    plt.savefig('01_monthly_video_count.png', dpi=300, bbox_inches='tight')
    logger.info("✓ Saved: 01_monthly_video_count.png")
    plt.close()


# ============================================================================
# 3. VISUALIZATION 2: MONTHLY VIEWS
# ============================================================================

def plot_monthly_views(df: pd.DataFrame) -> None:
    """Line chart: total views aggregated by month"""
    logger.info("Creating monthly views chart...")

    monthly_views = df.groupby('month_name')['view_count'].sum().sort_index()

    fig, ax = plt.subplots(figsize=(14, 6))
    ax.plot(range(len(monthly_views)), monthly_views.values, marker='o', linewidth=2.5,
            markersize=8, color='darkgreen', markerfacecolor='lightgreen', markeredgewidth=2)

    ax.set_title('YouTube Claude Content: Total Views Per Month', fontsize=14, fontweight='bold')
    ax.set_xlabel('Month', fontsize=12)
    ax.set_ylabel('Total Views', fontsize=12)
    ax.set_xticks(range(len(monthly_views)))
    ax.set_xticklabels(monthly_views.index, rotation=45, ha='right')
    ax.grid(alpha=0.3)

    # Add value labels on points
    for i, (idx, val) in enumerate(monthly_views.items()):
        ax.text(i, val, f'{int(val/1e6)}M' if val >= 1e6 else f'{int(val/1e3)}K',
                ha='center', va='bottom', fontsize=9)

    plt.tight_layout()
    plt.savefig('02_monthly_views.png', dpi=300, bbox_inches='tight')
    logger.info("✓ Saved: 02_monthly_views.png")
    plt.close()


# ============================================================================
# 4. VISUALIZATION 3: TOP 10 CHANNELS
# ============================================================================

def plot_top_channels(df: pd.DataFrame) -> None:
    """Horizontal bar chart: top 10 channels by total views"""
    logger.info("Creating top channels chart...")

    channel_stats = df.groupby('channel_name').agg({
        'view_count': 'sum',
        'video_id': 'count'
    }).rename(columns={'video_id': 'video_count'})

    top_channels = channel_stats.nlargest(10, 'view_count')

    fig, ax = plt.subplots(figsize=(12, 7))
    bars = ax.barh(range(len(top_channels)), top_channels['view_count'].values,
                   color='coral', edgecolor='black', alpha=0.7)

    ax.set_yticks(range(len(top_channels)))
    ax.set_yticklabels(top_channels.index, fontsize=11)
    ax.set_xlabel('Total Views', fontsize=12)
    ax.set_title('Top 10 Channels by Total Views', fontsize=14, fontweight='bold')
    ax.grid(axis='x', alpha=0.3)

    # Add value labels on bars
    for i, (idx, row) in enumerate(top_channels.iterrows()):
        ax.text(row['view_count'], i, f"  {int(row['view_count']/1e6)}M ({int(row['video_count'])} videos)",
                va='center', fontsize=10)

    plt.tight_layout()
    plt.savefig('03_top_10_channels.png', dpi=300, bbox_inches='tight')
    logger.info("✓ Saved: 03_top_10_channels.png")
    plt.close()


# ============================================================================
# 5. VISUALIZATION 4: ENGAGEMENT vs SCALE
# ============================================================================

def plot_engagement_vs_scale(df: pd.DataFrame) -> None:
    """Scatter plot: log(channel_total_views) vs average_engagement_rate"""
    logger.info("Creating engagement vs scale chart...")

    # Calculate channel-level metrics
    channel_stats = df.groupby('channel_id').agg({
        'view_count': 'sum',
        'engagement_rate': 'mean',
        'channel_name': 'first'
    }).reset_index()

    # Remove outliers for better visualization
    channel_stats = channel_stats[channel_stats['view_count'] > 0]
    channel_stats['log_views'] = np.log10(channel_stats['view_count'])

    fig, ax = plt.subplots(figsize=(12, 7))
    scatter = ax.scatter(channel_stats['log_views'], channel_stats['engagement_rate'] * 100,
                        s=100, alpha=0.6, c=channel_stats['view_count'], cmap='viridis',
                        edgecolors='black', linewidth=0.5)

    ax.set_xlabel('log₁₀(Total Channel Views)', fontsize=12)
    ax.set_ylabel('Average Engagement Rate (%)', fontsize=12)
    ax.set_title('Engagement Rate vs Channel Scale\n(Larger channels vs smaller channels)',
                fontsize=14, fontweight='bold')
    ax.grid(alpha=0.3)

    cbar = plt.colorbar(scatter, ax=ax)
    cbar.set_label('Total Views', fontsize=11)

    plt.tight_layout()
    plt.savefig('04_engagement_vs_scale.png', dpi=300, bbox_inches='tight')
    logger.info("✓ Saved: 04_engagement_vs_scale.png")
    plt.close()


# ============================================================================
# 6. NLP ANALYSIS: WORD FREQUENCY
# ============================================================================

def extract_words(text: str, stop_words: set) -> list:
    """Extract and clean words from text"""
    if pd.isna(text):
        return []

    # Convert to lowercase and remove special characters
    text = text.lower()
    text = re.sub(r'[^\w\s]', '', text)
    words = text.split()

    # Filter out stopwords and short words
    return [w for w in words if w not in stop_words and len(w) > 2]


def plot_word_frequency_comparison(df: pd.DataFrame) -> None:
    """Compare word frequency: top 100 videos vs rest"""
    logger.info("Performing NLP analysis...")

    stop_words = set(stopwords.words('english'))
    stop_words.update(['claude', 'ai', 'youtube', 'video', 'new', 'best'])

    # Top 100 vs rest
    top_100 = df.nlargest(100, 'view_count')
    rest = df[~df['video_id'].isin(top_100['video_id'])]

    # Extract words
    top_words = []
    for title in top_100['title']:
        top_words.extend(extract_words(title, stop_words))

    rest_words = []
    for title in rest['title']:
        rest_words.extend(extract_words(title, stop_words))

    # Count frequencies
    top_counter = Counter(top_words)
    rest_counter = Counter(rest_words)

    top_20 = dict(top_counter.most_common(20))
    rest_20 = dict(rest_counter.most_common(20))

    # Visualization
    fig, axes = plt.subplots(1, 2, figsize=(16, 6))

    # Top 100 videos
    ax1 = axes[0]
    words_top = list(top_20.keys())
    counts_top = list(top_20.values())
    ax1.barh(words_top, counts_top, color='teal', edgecolor='black', alpha=0.7)
    ax1.set_xlabel('Frequency', fontsize=11)
    ax1.set_title('Top 100 Videos: Most Frequent Title Words', fontsize=12, fontweight='bold')
    ax1.grid(axis='x', alpha=0.3)

    # Rest of videos
    ax2 = axes[1]
    words_rest = list(rest_20.keys())
    counts_rest = list(rest_20.values())
    ax2.barh(words_rest, counts_rest, color='orange', edgecolor='black', alpha=0.7)
    ax2.set_xlabel('Frequency', fontsize=11)
    ax2.set_title(f'Remaining {len(rest)} Videos: Most Frequent Title Words', fontsize=12, fontweight='bold')
    ax2.grid(axis='x', alpha=0.3)

    plt.tight_layout()
    plt.savefig('05_word_frequency_comparison.png', dpi=300, bbox_inches='tight')
    logger.info("✓ Saved: 05_word_frequency_comparison.png")
    plt.close()

    return top_20, rest_20


# ============================================================================
# 7. INSIGHTS & SUMMARY
# ============================================================================

def print_insights(df: pd.DataFrame) -> None:
    """Calculate and print key insights"""
    logger.info("\n" + "="*70)
    logger.info("INSIGHTS & SUMMARY STATISTICS")
    logger.info("="*70)

    # Dataset Overview
    logger.info(f"\n📊 DATASET OVERVIEW:")
    logger.info(f"   Total Videos: {len(df):,}")
    logger.info(f"   Total Views: {df['view_count'].sum():,.0f}")
    logger.info(f"   Total Likes: {df['like_count'].sum():,.0f}")
    logger.info(f"   Total Comments: {df['comment_count'].sum():,.0f}")
    logger.info(f"   Date Range: {df['published_at'].min().date()} to {df['published_at'].max().date()}")
    logger.info(f"   Unique Channels: {df['channel_id'].nunique()}")

    # 1. VIRAL DENSITY
    logger.info(f"\n🚀 VIRAL DENSITY (Views per Video by Month):")
    monthly_density = df.groupby('month_name').agg({
        'view_count': ['sum', 'count']
    })
    monthly_density.columns = ['total_views', 'video_count']
    monthly_density['viral_density'] = monthly_density['total_views'] / monthly_density['video_count']
    monthly_density = monthly_density.sort_values('viral_density', ascending=False)

    best_month = monthly_density.index[0]
    best_density = monthly_density['viral_density'].iloc[0]
    logger.info(f"   Peak Month: {best_month}")
    logger.info(f"   Views/Video: {best_density:,.0f}")
    logger.info(f"   Videos in that month: {int(monthly_density['video_count'].iloc[0])}")

    # Top 3 months
    logger.info(f"\n   Top 3 Months by Viral Density:")
    for i, (month, row) in enumerate(monthly_density.head(3).iterrows(), 1):
        logger.info(f"   {i}. {month}: {row['viral_density']:,.0f} views/video ({int(row['video_count'])} videos)")

    # 2. MOST EFFICIENT CHANNELS
    logger.info(f"\n⚡ MOST EFFICIENT CHANNELS (Highest views with fewest videos):")
    channel_stats = df.groupby('channel_name').agg({
        'view_count': 'sum',
        'video_id': 'count'
    }).rename(columns={'video_id': 'video_count'})

    # Calculate efficiency score (views per video)
    channel_stats['efficiency'] = channel_stats['view_count'] / channel_stats['video_count']

    # Filter channels with at least 3 videos for meaningful comparison
    efficient_channels = channel_stats[channel_stats['video_count'] >= 3].sort_values('efficiency', ascending=False)

    logger.info(f"\n   Top 5 Efficient Channels (≥3 videos):")
    for i, (channel, row) in enumerate(efficient_channels.head(5).iterrows(), 1):
        logger.info(f"   {i}. {channel}")
        logger.info(f"      Views: {int(row['view_count']):,} | Videos: {int(row['video_count'])} | Avg views/video: {int(row['efficiency']):,}")

    # 3. ENGAGEMENT METRICS
    logger.info(f"\n💬 ENGAGEMENT METRICS:")
    avg_engagement = df['engagement_rate'].mean() * 100
    avg_like_rate = df['like_rate'].mean() * 100
    avg_comment_rate = df['comment_rate'].mean() * 100

    logger.info(f"   Average Engagement Rate: {avg_engagement:.2f}%")
    logger.info(f"   Average Like Rate: {avg_like_rate:.2f}%")
    logger.info(f"   Average Comment Rate: {avg_comment_rate:.2f}%")

    # Top engagement videos
    top_engagement = df.nlargest(3, 'engagement_rate')[['title', 'view_count', 'engagement_rate']]
    logger.info(f"\n   Most Engaging Videos:")
    for i, (idx, row) in enumerate(top_engagement.iterrows(), 1):
        logger.info(f"   {i}. {row['title'][:60]}...")
        logger.info(f"      Views: {int(row['view_count']):,} | Engagement: {row['engagement_rate']*100:.2f}%")

    # 4. VIEW DISTRIBUTION
    logger.info(f"\n📈 VIEW DISTRIBUTION:")
    logger.info(f"   Median Views: {df['view_count'].median():,.0f}")
    logger.info(f"   Mean Views: {df['view_count'].mean():,.0f}")
    logger.info(f"   Max Views: {df['view_count'].max():,.0f}")
    logger.info(f"   Min Views: {df['view_count'].min():,.0f}")
    logger.info(f"   Std Dev: {df['view_count'].std():,.0f}")

    # 5. CONTENT INSIGHTS
    logger.info(f"\n🎬 CONTENT INSIGHTS:")
    logger.info(f"   Average Title Length: {df['title'].str.len().mean():.1f} characters")
    logger.info(f"   Videos with Tags: {df['tags'].notna().sum():,} ({df['tags'].notna().sum()/len(df)*100:.1f}%)")

    logger.info("\n" + "="*70)


# ============================================================================
# 8. MAIN EXECUTION
# ============================================================================

def main():
    """Main analysis pipeline"""
    logger.info("Starting YouTube Claude AI Content Analysis...")

    # Load and clean data
    df = load_and_clean_data('youtube_claude_data.csv')

    # Create visualizations
    plot_monthly_video_count(df)
    plot_monthly_views(df)
    plot_top_channels(df)
    plot_engagement_vs_scale(df)
    top_words, rest_words = plot_word_frequency_comparison(df)

    # Print insights
    print_insights(df)

    logger.info("\n✅ Analysis complete! Check PNG files for visualizations.")
    logger.info("   Generated files:")
    logger.info("   - 01_monthly_video_count.png")
    logger.info("   - 02_monthly_views.png")
    logger.info("   - 03_top_10_channels.png")
    logger.info("   - 04_engagement_vs_scale.png")
    logger.info("   - 05_word_frequency_comparison.png")


if __name__ == '__main__':
    main()
