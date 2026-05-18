# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- `scripts/maintenance.py` — standalone Python web server that serves a styled "screen-mgr restarting" page on configurable port for a configurable duration. Page auto-refreshes every 2s and sends `Cache-Control: no-store`, so connected browsers automatically return to the real admin once it comes back up. Designed to be called by the future deploy script to bridge the restart gap.

### Changed
- `.gitignore` — added explicit patterns for `.env`, `.env.*`, `*.key`, `*.pem`, `id_ed25519*`, `id_rsa*`, `authorized_keys` to harden against accidental secret commits.

### Fixed
- WebSocket handler now returns early when `ConnectionManager.connect()` rejects a connection, preventing the receive loop from running on a rejected socket (`routes/websocket_routes.py`)
- News presentation template no longer renders an empty `.p-bg`/`.p-overlay` when an article has no image (`templates/content/news_presentation.html`)
