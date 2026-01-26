import re
from datetime import datetime
from typing import List, Optional
from .models import NewsSource, NewsArticle
from .manager import news_manager

try:
    import feedparser
    # Test that feedparser actually works
    _ = feedparser.parse
    FEEDPARSER_AVAILABLE = True
except (ImportError, ModuleNotFoundError, AttributeError) as e:
    FEEDPARSER_AVAILABLE = False
    print(f"Warning: feedparser not available ({e}). RSS fetching disabled.")

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False
    print("Warning: httpx not installed. API fetching disabled.")


def parse_date(date_str: str) -> Optional[datetime]:
    """Try to parse various date formats"""
    if not date_str:
        return None

    try:
        from dateutil import parser
        return parser.parse(date_str)
    except ImportError:
        pass
    except Exception:
        pass

    # Fallback: try common formats
    formats = [
        "%a, %d %b %Y %H:%M:%S %z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return None


def clean_html(text: str) -> str:
    """Remove HTML tags from text"""
    if not text:
        return ""
    clean = re.sub(r'<[^>]+>', '', text)
    clean = re.sub(r'\s+', ' ', clean).strip()
    return clean[:500]  # Limit summary length


def extract_image_from_entry(entry) -> Optional[str]:
    """Try to extract an image URL from an RSS entry"""
    # Check media:content
    if hasattr(entry, 'media_content') and entry.media_content:
        for media in entry.media_content:
            if media.get('type', '').startswith('image'):
                return media.get('url')

    # Check media:thumbnail
    if hasattr(entry, 'media_thumbnail') and entry.media_thumbnail:
        return entry.media_thumbnail[0].get('url')

    # Check enclosures
    if hasattr(entry, 'enclosures') and entry.enclosures:
        for enc in entry.enclosures:
            if enc.get('type', '').startswith('image'):
                return enc.get('href') or enc.get('url')

    # Try to find image in content
    content = ''
    if hasattr(entry, 'content') and entry.content:
        content = entry.content[0].get('value', '')
    elif hasattr(entry, 'summary'):
        content = entry.summary or ''

    img_match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', content)
    if img_match:
        return img_match.group(1)

    return None


def fetch_rss_feed(source: NewsSource) -> List[NewsArticle]:
    """Fetch articles from an RSS feed"""
    if not FEEDPARSER_AVAILABLE:
        print(f"Cannot fetch {source.name}: feedparser not installed")
        return []

    articles = []
    try:
        feed = feedparser.parse(source.url)

        for entry in feed.entries[:20]:  # Limit to 20 most recent
            title = entry.get('title', 'No title')
            link = entry.get('link', '')

            if not link:
                continue

            summary = clean_html(entry.get('summary', entry.get('description', '')))
            published = parse_date(entry.get('published', entry.get('updated', '')))
            image_url = extract_image_from_entry(entry)

            article = NewsArticle(
                source_id=source.id,
                source_name=source.name,
                title=title,
                summary=summary,
                image_url=image_url,
                article_url=link,
                published_date=published,
            )
            articles.append(article)

    except Exception as e:
        print(f"Error fetching RSS feed {source.name}: {e}")

    return articles


async def fetch_source(source: NewsSource) -> List[NewsArticle]:
    """Fetch articles from a source based on its type"""
    if source.type == "rss":
        return fetch_rss_feed(source)
    elif source.type == "api":
        # API fetching could be implemented here
        print(f"API fetching not yet implemented for {source.name}")
        return []
    elif source.type == "manual":
        # Manual sources don't auto-fetch
        return []
    return []


async def fetch_all_sources() -> int:
    """Fetch articles from all enabled sources"""
    sources = news_manager.get_sources(enabled_only=True)
    total_new = 0

    for source in sources:
        print(f"Fetching from {source.name}...")
        articles = await fetch_source(source)

        for article in articles:
            existing = next((a for a in news_manager.articles if a.article_url == article.article_url), None)
            if not existing:
                news_manager.add_article(article)
                total_new += 1

        # Update last_fetched
        source.last_fetched = datetime.now()
        news_manager.save_sources()

    print(f"Fetched {total_new} new articles")
    return total_new


def fetch_all_sources_sync() -> int:
    """Synchronous wrapper for fetch_all_sources"""
    import asyncio
    return asyncio.run(fetch_all_sources())
