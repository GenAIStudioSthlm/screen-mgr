import json
import os
from datetime import datetime, timedelta
from typing import List, Optional
from pydantic import ValidationError
from .models import NewsSource, NewsArticle, NewsPlaylist, ArticleStatus

DATA_DIR = "data"
SOURCES_FILE = os.path.join(DATA_DIR, "news_sources.json")
ARTICLES_FILE = os.path.join(DATA_DIR, "news_articles.json")
PLAYLISTS_FILE = os.path.join(DATA_DIR, "news_playlists.json")


class NewsManager:
    def __init__(self):
        self.sources: List[NewsSource] = []
        self.articles: List[NewsArticle] = []
        self.playlists: List[NewsPlaylist] = []
        self._ensure_data_dir()
        self.load_all()

    def _ensure_data_dir(self):
        if not os.path.exists(DATA_DIR):
            os.makedirs(DATA_DIR)

    # === Loading ===
    def load_all(self):
        self.load_sources()
        self.load_articles()
        self.load_playlists()

    def load_sources(self):
        try:
            with open(SOURCES_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)
                self.sources = [NewsSource(**s) for s in raw]
        except FileNotFoundError:
            self.sources = self._create_default_sources()
            self.save_sources()
        except (ValidationError, json.JSONDecodeError) as e:
            print(f"Error loading news sources: {e}")
            self.sources = []

    def load_articles(self):
        try:
            with open(ARTICLES_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)
                self.articles = [NewsArticle(**a) for a in raw]
        except FileNotFoundError:
            self.articles = []
        except (ValidationError, json.JSONDecodeError) as e:
            print(f"Error loading news articles: {e}")
            self.articles = []

    def load_playlists(self):
        try:
            with open(PLAYLISTS_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)
                self.playlists = [NewsPlaylist(**p) for p in raw]
        except FileNotFoundError:
            self.playlists = []
        except (ValidationError, json.JSONDecodeError) as e:
            print(f"Error loading news playlists: {e}")
            self.playlists = []

    # === Saving ===
    def save_sources(self):
        with open(SOURCES_FILE, "w", encoding="utf-8") as f:
            json.dump([s.model_dump(mode="json") for s in self.sources], f, indent=2, default=str)

    def save_articles(self):
        with open(ARTICLES_FILE, "w", encoding="utf-8") as f:
            json.dump([a.model_dump(mode="json") for a in self.articles], f, indent=2, default=str)

    def save_playlists(self):
        with open(PLAYLISTS_FILE, "w", encoding="utf-8") as f:
            json.dump([p.model_dump(mode="json") for p in self.playlists], f, indent=2, default=str)

    # === Default Sources ===
    def _create_default_sources(self) -> List[NewsSource]:
        return [
            NewsSource(
                name="MIT Technology Review - AI",
                type="rss",
                url="https://www.technologyreview.com/feed/",
                category="Industry News",
                priority=8
            ),
            NewsSource(
                name="ArXiv AI",
                type="rss",
                url="https://rss.arxiv.org/rss/cs.AI",
                category="Research",
                priority=9
            ),
            NewsSource(
                name="OpenAI Blog",
                type="rss",
                url="https://openai.com/blog/rss/",
                category="Industry News",
                priority=8
            ),
        ]

    # === Source CRUD ===
    def get_sources(self, enabled_only: bool = False) -> List[NewsSource]:
        if enabled_only:
            return [s for s in self.sources if s.enabled]
        return self.sources

    def get_source(self, source_id: str) -> Optional[NewsSource]:
        return next((s for s in self.sources if s.id == source_id), None)

    def add_source(self, source: NewsSource) -> NewsSource:
        self.sources.append(source)
        self.save_sources()
        return source

    def update_source(self, source_id: str, updates: dict) -> Optional[NewsSource]:
        source = self.get_source(source_id)
        if source:
            for key, value in updates.items():
                if hasattr(source, key):
                    setattr(source, key, value)
            self.save_sources()
        return source

    def delete_source(self, source_id: str) -> bool:
        source = self.get_source(source_id)
        if source:
            self.sources.remove(source)
            self.save_sources()
            return True
        return False

    # === Article CRUD ===
    def get_articles(self, status: Optional[ArticleStatus] = None, category: Optional[str] = None, content_type: Optional[str] = None, limit: int = 50) -> List[NewsArticle]:
        articles = self.articles
        if status:
            articles = [a for a in articles if a.status == status]
        if category:
            articles = [a for a in articles if getattr(a, 'category', 'General') == category]
        if content_type:
            articles = [a for a in articles if getattr(a, 'content_type', 'article') == content_type]
        # Sort by published date descending
        articles = sorted(articles, key=lambda a: a.published_date or a.fetched_date, reverse=True)
        return articles[:limit]

    def get_approved_articles(self, category: Optional[str] = None, limit: int = 20) -> List[NewsArticle]:
        """Get approved and featured articles for display"""
        approved = [a for a in self.articles if a.status in (ArticleStatus.APPROVED, ArticleStatus.FEATURED)]
        if category:
            approved = [a for a in approved if getattr(a, 'category', 'General') == category]
        # Featured first, then by date
        approved = sorted(approved, key=lambda a: (a.status != ArticleStatus.FEATURED, -(a.published_date or a.fetched_date).timestamp()))
        return approved[:limit]

    def get_categories(self) -> List[str]:
        """Get all unique categories from articles"""
        categories = set()
        for article in self.articles:
            cat = getattr(article, 'category', 'General')
            if cat:
                categories.add(cat)
        return sorted(list(categories))

    def get_article(self, article_id: str) -> Optional[NewsArticle]:
        return next((a for a in self.articles if a.id == article_id), None)

    def add_article(self, article: NewsArticle) -> NewsArticle:
        # Check for duplicate by URL
        existing = next((a for a in self.articles if a.article_url == article.article_url), None)
        if existing:
            return existing
        self.articles.append(article)
        self.save_articles()
        return article

    def update_article(self, article_id: str, updates: dict) -> Optional[NewsArticle]:
        article = self.get_article(article_id)
        if article:
            for key, value in updates.items():
                if hasattr(article, key):
                    setattr(article, key, value)
            self.save_articles()
        return article

    def delete_article(self, article_id: str) -> bool:
        article = self.get_article(article_id)
        if article:
            self.articles.remove(article)
            self.save_articles()
            return True
        return False

    def approve_article(self, article_id: str) -> Optional[NewsArticle]:
        return self.update_article(article_id, {"status": ArticleStatus.APPROVED})

    def reject_article(self, article_id: str) -> Optional[NewsArticle]:
        return self.update_article(article_id, {"status": ArticleStatus.REJECTED})

    def feature_article(self, article_id: str) -> Optional[NewsArticle]:
        return self.update_article(article_id, {"status": ArticleStatus.FEATURED})

    def bulk_add_articles(self, articles: List[NewsArticle]):
        for article in articles:
            self.add_article(article)

    # === Playlist CRUD ===
    def get_playlists(self, active_only: bool = False) -> List[NewsPlaylist]:
        if active_only:
            return [p for p in self.playlists if p.active]
        return self.playlists

    def get_playlist(self, playlist_id: str) -> Optional[NewsPlaylist]:
        return next((p for p in self.playlists if p.id == playlist_id), None)

    def get_active_playlist(self) -> Optional[NewsPlaylist]:
        """Get the currently active playlist"""
        active = [p for p in self.playlists if p.active]
        if active:
            # Return most recent active playlist
            return sorted(active, key=lambda p: (p.year, p.week_number), reverse=True)[0]
        return None

    def get_playlist_articles(self, playlist_id: str) -> List[NewsArticle]:
        """Get articles in a playlist, in order"""
        playlist = self.get_playlist(playlist_id)
        if not playlist:
            return []
        articles = []
        for aid in playlist.article_ids:
            article = self.get_article(aid)
            if article:
                articles.append(article)
        return articles

    def create_playlist(self, name: str, week_number: int, year: int) -> NewsPlaylist:
        playlist = NewsPlaylist(name=name, week_number=week_number, year=year)
        self.playlists.append(playlist)
        self.save_playlists()
        return playlist

    def add_article_to_playlist(self, playlist_id: str, article_id: str) -> bool:
        playlist = self.get_playlist(playlist_id)
        if playlist and article_id not in playlist.article_ids:
            playlist.article_ids.append(article_id)
            self.save_playlists()
            return True
        return False

    def remove_article_from_playlist(self, playlist_id: str, article_id: str) -> bool:
        playlist = self.get_playlist(playlist_id)
        if playlist and article_id in playlist.article_ids:
            playlist.article_ids.remove(article_id)
            self.save_playlists()
            return True
        return False

    def delete_playlist(self, playlist_id: str) -> bool:
        playlist = self.get_playlist(playlist_id)
        if playlist:
            self.playlists.remove(playlist)
            self.save_playlists()
            return True
        return False

    def set_active_playlist(self, playlist_id: str) -> bool:
        """Set a playlist as active, deactivating others"""
        for p in self.playlists:
            p.active = (p.id == playlist_id)
        self.save_playlists()
        return True

    # === Utility ===
    def create_weekly_playlist_from_approved(self) -> NewsPlaylist:
        """Create a new weekly playlist from currently approved articles"""
        now = datetime.now()
        week = now.isocalendar()[1]
        year = now.year

        playlist = self.create_playlist(
            name=f"Week {week} - {year}",
            week_number=week,
            year=year
        )

        approved = self.get_approved_articles(limit=10)
        for article in approved:
            self.add_article_to_playlist(playlist.id, article.id)

        self.set_active_playlist(playlist.id)
        return playlist

    def cleanup_expired_articles(self, days_old: int = 30):
        """Remove articles older than specified days"""
        cutoff = datetime.now() - timedelta(days=days_old)
        self.articles = [a for a in self.articles if (a.fetched_date or datetime.now()) > cutoff]
        self.save_articles()


# Singleton instance
news_manager = NewsManager()
