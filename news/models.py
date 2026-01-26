from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field
from enum import Enum
import uuid


class SourceType(str, Enum):
    RSS = "rss"
    API = "api"
    MANUAL = "manual"


class ArticleStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    FEATURED = "featured"


class NewsMode(str, Enum):
    PORTRAIT = "portrait"
    LANDSCAPE = "landscape"
    PRESENTATION = "presentation"


class NewsSource(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = Field(..., description="Display name for the source")
    type: SourceType = Field(default=SourceType.RSS)
    url: str = Field(..., description="RSS feed URL or API endpoint")
    category: str = Field(default="General", description="Category for grouping")
    enabled: bool = Field(default=True)
    fetch_interval_hours: int = Field(default=24)
    last_fetched: Optional[datetime] = Field(default=None)
    priority: int = Field(default=5, ge=1, le=10)

    class Config:
        use_enum_values = True


class NewsArticle(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_id: str = Field(..., description="ID of the source this article came from")
    source_name: str = Field(default="", description="Name of the source for display")
    title: str = Field(..., description="Article title")
    summary: str = Field(default="", max_length=500)
    image_url: Optional[str] = Field(default=None)
    article_url: str = Field(..., description="Link to full article")
    published_date: Optional[datetime] = Field(default=None)
    fetched_date: datetime = Field(default_factory=datetime.now)
    expires_date: Optional[datetime] = Field(default=None)
    status: ArticleStatus = Field(default=ArticleStatus.PENDING)
    display_duration_seconds: int = Field(default=15)

    class Config:
        use_enum_values = True


class NewsPlaylist(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = Field(..., description="Playlist name")
    week_number: int = Field(..., ge=1, le=53)
    year: int = Field(...)
    article_ids: List[str] = Field(default_factory=list)
    created_date: datetime = Field(default_factory=datetime.now)
    active: bool = Field(default=True)

    class Config:
        use_enum_values = True
