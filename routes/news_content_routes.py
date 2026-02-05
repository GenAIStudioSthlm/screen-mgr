# News content display routes
from datetime import datetime
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from news import news_manager

templates = Jinja2Templates(directory="templates")
# Add datetime to template globals for week number display
templates.env.globals["now"] = datetime.now
router = APIRouter(prefix="/news", tags=["news-content"])


@router.get("/portrait", response_class=HTMLResponse)
@router.get("/portrait/{playlist_id}", response_class=HTMLResponse)
async def news_portrait(request: Request, playlist_id: str = None):
    """Display news in portrait mode (vertical screens)"""
    articles = _get_display_articles(playlist_id)
    return templates.TemplateResponse(
        "content/news_portrait.html",
        {
            "request": request,
            "articles": articles,
            "mode": "portrait",
            "rotation_seconds": 15,
        },
    )


@router.get("/landscape", response_class=HTMLResponse)
@router.get("/landscape/{playlist_id}", response_class=HTMLResponse)
async def news_landscape(request: Request, playlist_id: str = None):
    """Display news in landscape mode (horizontal screens)"""
    articles = _get_display_articles(playlist_id)
    return templates.TemplateResponse(
        "content/news_landscape.html",
        {
            "request": request,
            "articles": articles,
            "mode": "landscape",
            "rotation_seconds": 15,
        },
    )


@router.get("/presentation", response_class=HTMLResponse)
@router.get("/presentation/{playlist_id}", response_class=HTMLResponse)
async def news_presentation(request: Request, playlist_id: str = None):
    """Display news in presentation mode (meetings/demos)"""
    articles = _get_display_articles(playlist_id)
    return templates.TemplateResponse(
        "content/news_presentation.html",
        {
            "request": request,
            "articles": articles,
            "mode": "presentation",
            "rotation_seconds": 30,
        },
    )


@router.get("/article/{article_id}", response_class=HTMLResponse)
async def news_article_reader(request: Request, article_id: str, mode: str = "vertical"):
    """Display a single article in the tech-noir reader with 3 viewing modes"""
    article = news_manager.get_article(article_id)
    if not article:
        return HTMLResponse("<h1>Article not found</h1>", status_code=404)

    # Build readable content from summary (full article text lives at article_url)
    content_text = article.summary or ""

    # Estimate read time (~200 words per minute)
    word_count = len(content_text.split())
    minutes = max(1, round(word_count / 200))
    read_time = f"{minutes} min read"

    return templates.TemplateResponse(
        "content/news_article_reader.html",
        {
            "request": request,
            "article": article,
            "content_text": content_text,
            "read_time": read_time,
            "mode": mode,
        },
    )


@router.get("/api/articles", response_class=JSONResponse)
async def get_news_articles(playlist_id: str = None):
    """Get articles as JSON for dynamic updates"""
    articles = _get_display_articles(playlist_id)
    return [
        {
            "id": a.id,
            "title": a.title,
            "summary": a.summary,
            "image_url": a.image_url,
            "article_url": a.article_url,
            "source_name": a.source_name,
            "published_date": a.published_date.isoformat() if a.published_date else None,
            "status": a.status,
        }
        for a in articles
    ]


def _get_display_articles(playlist_id: str = None):
    """Get articles for display - from playlist or approved articles"""
    if playlist_id:
        articles = news_manager.get_playlist_articles(playlist_id)
        if articles:
            return articles

    # Fall back to active playlist
    active_playlist = news_manager.get_active_playlist()
    if active_playlist:
        articles = news_manager.get_playlist_articles(active_playlist.id)
        if articles:
            return articles

    # Fall back to all approved articles
    return news_manager.get_approved_articles(limit=10)
