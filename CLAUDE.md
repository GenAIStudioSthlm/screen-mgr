# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Screen-mgr is a Multi-Screen Content Manager built with FastAPI that manages and displays content across multiple digital screens in real-time. It uses WebSockets for instant updates and supports various content types including text, URLs, videos, pictures, PDFs, and slideshows.

## Development Commands

### Setup and Run
```bash
# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # macOS/Linux
# or: venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Run development server with auto-reload
uvicorn main:app --reload

# Run on specific host/port
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### Python Code Quality
```bash
# No linting or formatting tools are configured yet
# Consider running manually if needed:
# python -m flake8 .
# python -m black .
```

## Architecture Overview

### Core Components

1. **Screen Management System** (`screens.py`)
   - `Screen` model: Defines content types and screen properties
   - `ScreenManager`: Singleton managing all screen states and configurations
   - Persistence: JSON file storage in `screens.json`
   - Default: 6 screens pre-configured

2. **WebSocket Connection Management** (`connections.py`)
   - `ConnectionManager`: Handles real-time connections
   - Manages both screen connections and admin panel connections
   - Broadcasts updates to all connected clients
   - Tracks connection status for each screen

3. **Route Organization** (`routes/`)
   - `admin.py`: Admin panel UI and management endpoints
   - `api.py`: RESTful API for programmatic access
   - `websocket.py`: WebSocket endpoints for real-time communication
   - `content.py`: Content serving (videos, PDFs, pictures)
   - `screens.py`: Individual screen display pages

### Key Design Patterns

- **Singleton Pattern**: Single instances of `screen_manager` and `connection_manager` shared across the application
- **WebSocket Broadcasting**: All screen updates are instantly pushed to connected clients
- **File-based Storage**: Simple JSON persistence without database dependencies
- **Static File Serving**: Direct serving of media content from filesystem

### Content Types and Handling

- **Text**: Direct display of text content
- **URL**: External web page embedding
- **Video**: MP4 files stored in `static/videos/`
- **Picture**: PNG, JPG, GIF files in `static/pictures/` (supports subfolders)
- **PDF**: PDF files in `static/pdfs/`
- **Slideshow**: Rotating display of images from selected folder

### WebSocket Protocol

Screens connect via WebSocket to `/ws/{screen_id}` and receive JSON messages:
```json
{
  "type": "content_type",
  "content": "content_value",
  "background_color": "#000000"
}
```

Admin updates trigger broadcasts to all connected screens for the updated screen ID.

## Important Considerations

- **No Authentication**: Admin panel is currently unprotected
- **No Tests**: No testing infrastructure exists yet
- **File Storage**: All media files are stored locally in `static/` subdirectories
- **Screen IDs**: Screens are identified by integer IDs (1-6 by default)
- **Real-time Updates**: WebSocket connections enable instant content updates without page refresh
- **Error Handling**: Basic error handling exists but could be enhanced for production use

## MCP Server Integration

The project includes an MCP (Model Context Protocol) server for programmatic control of screens.

### MCP Setup
```bash
# Install MCP dependencies (already in requirements.txt)
pip install mcp httpx

# Test MCP server functionality
python test_mcp.py

# Start MCP server (requires Screen Manager to be running)
python start_mcp.py
```

### Available MCP Tools

**Screen Query Operations:**
- `list_screens` - List all screens with status and content
- `get_screen(screen_id)` - Get detailed info for specific screen

**Screen Control Operations:**
- `set_screen_content(screen_id, content_type, content, ...)` - Update screen content
- `set_all_screens_content(content_type, content, ...)` - Update all screens
- `display_text(screen_id, text, background_color)` - Show text on screen
- `display_url(screen_id, url)` - Show website on screen
- `display_youtube(screen_id, video_id)` - Show YouTube video
- `create_slideshow(screen_id, folder, interval)` - Create picture slideshow

**Content Management:**
- `list_content(content_type)` - List available pictures/videos/PDFs

### MCP Configuration

Configure your MCP client with:
```json
{
  "mcpServers": {
    "screen-manager": {
      "command": "python",
      "args": ["start_mcp.py"],
      "env": {
        "SCREEN_MANAGER_URL": "http://localhost:8000"
      }
    }
  }
}
```

## Common Development Tasks

When modifying screen behavior:
1. Update the `Screen` model in `screens.py` for new properties
2. Modify WebSocket message handling in `static/js/screen.js`
3. Update admin panel UI in `templates/admin.html` and `static/js/admin.js`
4. Ensure `ConnectionManager` broadcasts changes appropriately
5. Update MCP server tools in `mcp/server.py` if adding new functionality

When adding new content types:
1. Add to `Screen.type` enum in `screens.py`
2. Implement display logic in `static/js/screen.js`
3. Add upload/management UI in admin panel
4. Create appropriate route in `routes/content.py` if needed
5. Add MCP tool support in `mcp/server.py`