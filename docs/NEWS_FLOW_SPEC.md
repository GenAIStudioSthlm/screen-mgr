# AI News Flow Feature Specification

**Status:** Planning
**Branch:** `staging/news-flow-feature`
**Created:** 2026-01-26

---

## Overview

A new content type that aggregates and displays AI-related news articles and research reports from curated sources, updated weekly, with support for portrait, landscape, and presentation screen orientations.

---

## 1. Functional Requirements

### 1.1 News Source Management

**Admin capabilities:**
- Add/remove news sources (RSS feeds, websites, APIs)
- Categorize sources (e.g., "Research Papers", "Industry News", "Tutorials")
- Set source priority/weight for display ordering
- Enable/disable individual sources without deleting them

**Suggested source types:**

| Type | Examples |
|------|----------|
| RSS Feeds | ArXiv AI, MIT Tech Review, The Verge AI |
| APIs | HackerNews API, Reddit API (r/MachineLearning) |
| Research | ArXiv, Papers With Code, Semantic Scholar |
| News Sites | TechCrunch AI, VentureBeat AI |

### 1.2 Article Management

**System should:**
- Fetch articles from sources on a configurable schedule (default: daily)
- Store article metadata: title, summary, source, date, image, URL
- Allow manual curation (approve/reject/feature articles)
- Support manual article addition (for reports not in feeds)
- Auto-expire articles after configurable period (default: 2 weeks)

**Admin should be able to:**
- View all fetched articles
- Mark articles as "featured" for priority display
- Edit article display text/summary
- Set display duration per article
- Create "weekly digest" playlists manually or automatically

---

## 2. Display Modes

Three display modes available:

| Mode | Orientation | Use Case |
|------|-------------|----------|
| Portrait | Vertical | Standing screens, kiosks |
| Landscape | Horizontal | Wall-mounted wide screens |
| Presentation | Horizontal only | Meetings, demos, main displays |

### 2.1 Portrait Mode (Standing Screens)

```
┌─────────────────┐
│   NEWS HEADER   │
│                 │
│  ┌───────────┐  │
│  │   IMAGE   │  │
│  │           │  │
│  └───────────┘  │
│                 │
│  Article Title  │
│  (large text)   │
│                 │
│  Summary text   │
│  2-3 lines max  │
│                 │
│  Source • Date  │
│                 │
│  ● ○ ○ ○ ○     │
│  (pagination)   │
└─────────────────┘
```

### 2.2 Landscape Mode (Wide Screens)

```
┌────────────────────────────────────────────────┐
│  AI NEWS                              Week 4   │
├──────────────────────┬─────────────────────────┤
│                      │  Article Title          │
│      IMAGE           │                         │
│                      │  Summary text that can  │
│                      │  be longer in this      │
│                      │  format, 4-5 lines      │
│                      │                         │
│                      │  Source • Jan 26, 2026  │
├──────────────────────┴─────────────────────────┤
│  ● ○ ○ ○ ○ ○ ○ ○                              │
└────────────────────────────────────────────────┘
```

### 2.3 Presentation Mode (Meetings/Demos) - Landscape Only

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                                                                              │
│      ┌─────────────────────────────────────────────────────────────────┐     │
│      │                                                                 │     │
│      │                        LARGE IMAGE                              │     │
│      │                      (hero banner)                              │     │
│      │                                                                 │     │
│      └─────────────────────────────────────────────────────────────────┘     │
│                                                                              │
│                         Article Title Goes Here                              │
│                           (large, centered)                                  │
│                                                                              │
│           Summary text with more room to breathe. Can span multiple          │
│           lines and include more context about the article.                  │
│                                                                              │
│                        ━━━━━━━━━━━━━━━━━━━━━━━                               │
│                                                                              │
│                    MIT Technology Review • Jan 26, 2026                      │
│                                                                              │
│      ┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐                       │
│      │  01  │  │  02  │  │ ●03 │  │  04  │  │  05  │    AI NEWS WEEKLY      │
│      └──────┘  └──────┘  └──────┘  └──────┘  └──────┘    Week 4 • 2026       │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

**Presentation mode features:**
- Larger typography (readable from 5+ meters)
- Hero image takes ~40% of screen height
- More whitespace/padding
- Numbered article indicators (not just dots)
- Longer rotation time (default: 30 seconds)
- Optional QR code to article
- Manual navigation support (pause, prev/next)

---

## 3. Data Model

### 3.1 New Entities

**NewsSource:**
```
- id: string (uuid)
- name: string
- type: enum (rss, api, manual)
- url: string
- category: string
- enabled: boolean
- fetch_interval_hours: int (default: 24)
- last_fetched: datetime
- priority: int (1-10)
```

**NewsArticle:**
```
- id: string (uuid)
- source_id: string (foreign key)
- title: string
- summary: string (max 500 chars)
- image_url: string (optional)
- article_url: string
- published_date: datetime
- fetched_date: datetime
- expires_date: datetime
- status: enum (pending, approved, rejected, featured)
- display_duration_seconds: int (default: 15)
```

**NewsPlaylist (Weekly Digest):**
```
- id: string (uuid)
- name: string (e.g., "Week 4 - 2026")
- week_number: int
- year: int
- article_ids: list[string]
- created_date: datetime
- active: boolean
```

### 3.2 Screen Model Extension

Add to existing Screen model:
```
- type: "news" (new content type option)
- news_playlist_id: string (optional, for specific playlist)
- news_mode: enum (portrait, landscape, presentation)
- news_rotation_seconds: int (default: 15, presentation: 30)
- news_show_qr: boolean (default: false, presentation only)
- news_paused: boolean (default: false, runtime state)
```

---

## 4. New Routes & Endpoints

### 4.1 Admin Routes

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/admin/news` | News management dashboard |
| GET | `/admin/news/sources` | List/manage sources |
| POST | `/admin/news/sources` | Add new source |
| PUT | `/admin/news/sources/{id}` | Update source |
| DELETE | `/admin/news/sources/{id}` | Remove source |
| GET | `/admin/news/articles` | List all articles |
| PUT | `/admin/news/articles/{id}` | Update article status |
| POST | `/admin/news/articles` | Manually add article |
| GET | `/admin/news/playlists` | List weekly digests |
| POST | `/admin/news/playlists` | Create playlist |
| POST | `/admin/news/fetch` | Trigger manual fetch |

### 4.2 Content Routes

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/news/portrait` | Portrait display |
| GET | `/news/landscape` | Landscape display |
| GET | `/news/presentation` | Presentation display |
| GET | `/news/{mode}/{playlist_id}` | Specific playlist |

### 4.3 API Routes

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/news/articles` | Get current articles JSON |
| GET | `/api/news/playlists/{id}` | Get playlist details |

---

## 5. File Structure (New Files)

```
screen-mgr/
├── news/
│   ├── __init__.py
│   ├── models.py           # NewsSource, NewsArticle, NewsPlaylist
│   ├── fetcher.py          # RSS/API fetching logic
│   ├── scheduler.py        # Background job scheduling
│   └── manager.py          # CRUD operations
├── routes/
│   ├── news_routes.py      # Admin news management
│   └── news_content_routes.py  # Display endpoints
├── templates/
│   ├── admin/
│   │   ├── news_dashboard.html
│   │   ├── news_sources.html
│   │   ├── news_articles.html
│   │   └── news_playlists.html
│   └── content/
│       ├── news_portrait.html
│       ├── news_landscape.html
│       └── news_presentation.html
├── static/
│   └── javascript/
│       └── news.js         # Rotation logic, transitions
└── data/
    ├── news_sources.json
    ├── news_articles.json
    └── news_playlists.json
```

---

## 6. Dependencies to Add

```
# requirements.txt additions
feedparser>=6.0.0      # RSS parsing
httpx>=0.24.0          # Async HTTP client
apscheduler>=3.10.0    # Background job scheduling
python-dateutil>=2.8.0 # Date parsing
```

---

## 7. Admin UI for Presentation Control

When a screen is in presentation mode, admin gets extra controls:

```
┌─────────────────────────────────────────────────┐
│ PRESENTATION CONTROL - Main Screen              │
│                                                 │
│ Now showing: 3 of 8                             │
│ "OpenAI Releases GPT-5 Architecture Paper"      │
│                                                 │
│    [⏮ Prev]    [⏸ Pause]    [Next ⏭]           │
│                                                 │
│ Auto-advance in: 24s                            │
│                                                 │
│ Quick jump: [1] [2] [●3] [4] [5] [6] [7] [8]   │
│                                                 │
│ ☐ Show QR Code                                  │
└─────────────────────────────────────────────────┘
```

---

## 8. Background Jobs

**Required scheduled tasks:**

1. **Article Fetcher** (runs every 6 hours)
   - Iterates through enabled sources
   - Fetches new articles
   - Deduplicates by URL
   - Stores with "pending" status

2. **Article Expirer** (runs daily)
   - Marks expired articles as inactive
   - Deletes old articles after 30 days

3. **Weekly Digest Generator** (runs Sunday night)
   - Creates new playlist from top articles
   - Notifies admin of new digest ready

**Recommended:** APScheduler (integrates well with FastAPI)

---

## 9. Implementation Phases

- [ ] **Phase 1:** Data models and JSON storage
- [ ] **Phase 2:** RSS fetcher and article management
- [ ] **Phase 3:** Admin UI for sources and articles
- [ ] **Phase 4:** Portrait and landscape display templates
- [ ] **Phase 5:** Presentation mode with controls
- [ ] **Phase 6:** Background scheduler integration
- [ ] **Phase 7:** Testing and refinement
