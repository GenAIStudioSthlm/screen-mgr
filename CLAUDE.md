# Screen-Mgr - Multi-Screen Content Manager

FastAPI web app that manages content across multiple display screens with real-time WebSocket updates.

## Tech Stack
- **Backend**: FastAPI, Uvicorn, Jinja2, Pydantic
- **Frontend**: Vanilla JS, HTML, CSS
- **Data**: JSON-based config (screens.json)

## Running
```bash
uvicorn main:app --reload
```
- Admin panel: http://localhost:8000/admin
- Screen view: http://localhost:8000/screen/{id}

## Structure
- `main.py` - App entry point
- `routes.py` - API endpoints
- `screens.py` - Screen model & ScreenManager
- `connections.py` - WebSocket ConnectionManager
- `static/` - JS, pictures, videos, PDFs
- `templates/` - Jinja2 templates

## Content Types
text, url, video, picture, pdf, slideshow, screen_share

## Notes
- Never run build - it crashes the dev server
