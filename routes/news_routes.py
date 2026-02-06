# News management routes for admin panel
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from news import news_manager, NewsSource, NewsArticle, ContentType, CategoryType
from news.fetcher import fetch_all_sources

# Available categories for the dropdown
CATEGORIES = [e.value for e in CategoryType]
CONTENT_TYPES = [e.value for e in ContentType]

templates = Jinja2Templates(directory="templates")
router = APIRouter(prefix="/admin/news", tags=["news-admin"])


@router.get("", response_class=HTMLResponse)
async def news_dashboard(request: Request):
    """News management dashboard"""
    sources = news_manager.get_sources()
    articles = news_manager.get_articles(limit=50)
    playlists = news_manager.get_playlists()
    approved_count = len([a for a in articles if a.status in ("approved", "featured")])
    pending_count = len([a for a in articles if a.status == "pending"])

    return templates.TemplateResponse(
        "admin/news_dashboard.html",
        {
            "request": request,
            "sources": sources,
            "articles": articles,
            "playlists": playlists,
            "approved_count": approved_count,
            "pending_count": pending_count,
            "active_tab": "dashboard",
        },
    )


# === Sources ===
@router.get("/sources", response_class=HTMLResponse)
async def news_sources(request: Request):
    """List and manage news sources"""
    sources = news_manager.get_sources()
    return templates.TemplateResponse(
        "admin/news_sources.html",
        {"request": request, "sources": sources, "active_tab": "sources"},
    )


@router.post("/sources/add")
async def add_source(
    name: str = Form(...),
    url: str = Form(...),
    source_type: str = Form("rss"),
    category: str = Form("General"),
    priority: int = Form(5),
):
    """Add a new news source"""
    source = NewsSource(
        name=name,
        url=url,
        type=source_type,
        category=category,
        priority=priority,
    )
    news_manager.add_source(source)
    return RedirectResponse(url="/admin/news/sources", status_code=303)


@router.post("/sources/{source_id}/toggle")
async def toggle_source(source_id: str):
    """Enable/disable a source"""
    source = news_manager.get_source(source_id)
    if source:
        news_manager.update_source(source_id, {"enabled": not source.enabled})
    return RedirectResponse(url="/admin/news/sources", status_code=303)


@router.post("/sources/{source_id}/delete")
async def delete_source(source_id: str):
    """Delete a news source"""
    news_manager.delete_source(source_id)
    return RedirectResponse(url="/admin/news/sources", status_code=303)


# === Articles ===
@router.get("/articles", response_class=HTMLResponse)
async def news_articles(request: Request, status: str = None, category: str = None, content_type: str = None):
    """List and manage articles"""
    articles = news_manager.get_articles(status=status, category=category, content_type=content_type, limit=100)
    sources = news_manager.get_sources()
    return templates.TemplateResponse(
        "admin/news_articles.html",
        {
            "request": request,
            "articles": articles,
            "sources": sources,
            "current_status": status,
            "current_category": category,
            "current_content_type": content_type,
            "categories": CATEGORIES,
            "content_types": CONTENT_TYPES,
            "active_tab": "articles",
        },
    )


@router.post("/articles/add")
async def add_article(
    title: str = Form(...),
    summary: str = Form(""),
    article_url: str = Form(...),
    image_url: str = Form(""),
    source_name: str = Form("Manual"),
    content_type: str = Form("article"),
    category: str = Form("General"),
):
    """Manually add an article, video, or podcast"""
    article = NewsArticle(
        source_id="manual",
        source_name=source_name,
        title=title,
        summary=summary,
        article_url=article_url,
        image_url=image_url if image_url else None,
        content_type=content_type,
        category=category,
        status="approved",  # Manual items auto-approved
    )
    news_manager.add_article(article)
    return RedirectResponse(url="/admin/news/articles", status_code=303)


@router.post("/articles/{article_id}/approve")
async def approve_article(article_id: str, request: Request):
    """Approve an article for display"""
    news_manager.approve_article(article_id)
    # Stay on same page with same filters
    referer = request.headers.get("referer", "/admin/news/articles")
    return RedirectResponse(url=referer, status_code=303)


@router.post("/articles/{article_id}/reject")
async def reject_article(article_id: str, request: Request):
    """Reject an article"""
    news_manager.reject_article(article_id)
    referer = request.headers.get("referer", "/admin/news/articles")
    return RedirectResponse(url=referer, status_code=303)


@router.post("/articles/{article_id}/feature")
async def feature_article(article_id: str, request: Request):
    """Feature an article (priority display)"""
    news_manager.feature_article(article_id)
    referer = request.headers.get("referer", "/admin/news/articles")
    return RedirectResponse(url=referer, status_code=303)


@router.post("/articles/{article_id}/delete")
async def delete_article(article_id: str):
    """Delete an article"""
    news_manager.delete_article(article_id)
    return RedirectResponse(url="/admin/news/articles", status_code=303)


# === Playlists ===
@router.get("/playlists", response_class=HTMLResponse)
async def news_playlists(request: Request):
    """List and manage playlists"""
    playlists = news_manager.get_playlists()
    approved_articles = news_manager.get_approved_articles(limit=50)
    return templates.TemplateResponse(
        "admin/news_playlists.html",
        {
            "request": request,
            "playlists": playlists,
            "approved_articles": approved_articles,
            "active_tab": "playlists",
        },
    )


@router.post("/playlists/create")
async def create_playlist(
    name: str = Form(...),
    week_number: int = Form(...),
    year: int = Form(...),
):
    """Create a new playlist"""
    news_manager.create_playlist(name=name, week_number=week_number, year=year)
    return RedirectResponse(url="/admin/news/playlists", status_code=303)


@router.post("/playlists/generate")
async def generate_weekly_playlist():
    """Generate a weekly playlist from approved articles"""
    news_manager.create_weekly_playlist_from_approved()
    return RedirectResponse(url="/admin/news/playlists", status_code=303)


@router.post("/playlists/{playlist_id}/activate")
async def activate_playlist(playlist_id: str):
    """Set a playlist as active"""
    news_manager.set_active_playlist(playlist_id)
    return RedirectResponse(url="/admin/news/playlists", status_code=303)


@router.post("/playlists/{playlist_id}/add-article")
async def add_article_to_playlist(playlist_id: str, article_id: str = Form(...)):
    """Add an article to a playlist"""
    news_manager.add_article_to_playlist(playlist_id, article_id)
    return RedirectResponse(url="/admin/news/playlists", status_code=303)


@router.post("/playlists/{playlist_id}/remove-article/{article_id}")
async def remove_article_from_playlist(playlist_id: str, article_id: str):
    """Remove an article from a playlist"""
    news_manager.remove_article_from_playlist(playlist_id, article_id)
    return RedirectResponse(url="/admin/news/playlists", status_code=303)


@router.post("/playlists/{playlist_id}/delete")
async def delete_playlist(playlist_id: str):
    """Delete a playlist"""
    news_manager.delete_playlist(playlist_id)
    return RedirectResponse(url="/admin/news/playlists", status_code=303)


# === Fetch ===
@router.post("/fetch")
async def trigger_fetch():
    """Manually trigger article fetching from all sources"""
    count = await fetch_all_sources()
    print(f"Fetched {count} new articles")
    return RedirectResponse(url="/admin/news/articles?status=pending", status_code=303)
