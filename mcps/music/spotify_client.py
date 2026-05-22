"""Lazy Spotify client wrapper for the Music MCP.

Loads spotipy + credentials from .env (`SPOTIFY_CLIENT_ID`,
`SPOTIFY_CLIENT_SECRET`, `SPOTIFY_REFRESH_TOKEN`). Missing config or
missing dependency degrades to a clear error rather than crashing
the MCP server — tools return `{"error": "spotify not configured"}`
until the user runs the one-time `scripts/spotify_auth.py` flow and
puts the resulting refresh token in .env.

The token cache file is `data/spotify_token.json` (gitignored). The
refresh token in .env is what bootstraps the cache after a reboot.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional


# Scopes our MCP tools need. Keep tight — user grants exactly these
# when running the one-time auth helper.
SPOTIFY_SCOPES = (
    "user-read-playback-state "
    "user-modify-playback-state "
    "user-read-currently-playing"
)

TOKEN_CACHE = Path("data/spotify_token.json")


class NotConfigured(RuntimeError):
    """Raised when the Spotify env vars or the spotipy package are
    missing. Tools catch this and return a friendly error dict."""


def _need_env() -> tuple[str, str, Optional[str]]:
    client_id = os.environ.get("SPOTIFY_CLIENT_ID", "").strip()
    client_secret = os.environ.get("SPOTIFY_CLIENT_SECRET", "").strip()
    refresh_token = os.environ.get("SPOTIFY_REFRESH_TOKEN", "").strip() or None
    if not client_id or not client_secret:
        raise NotConfigured(
            "SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET must be set in "
            ".env (see docs/DEPLOY.md → Spotify setup)"
        )
    return client_id, client_secret, refresh_token


# Cached at module level so repeated tool calls don't re-build the
# spotipy client. Cheap to rebuild but slightly less hot-path noise.
_cached_client: Any = None


def get_client():
    """Return a fresh-token-refreshing spotipy.Spotify instance, or
    raise NotConfigured. Cached after first successful build."""
    global _cached_client
    if _cached_client is not None:
        return _cached_client

    try:
        import spotipy  # type: ignore
        from spotipy.oauth2 import SpotifyOAuth  # type: ignore
    except ImportError as e:
        raise NotConfigured(
            f"spotipy not installed in this venv: {e}. "
            f"Run `pip install spotipy` on the Pi."
        )

    client_id, client_secret, refresh_token = _need_env()

    TOKEN_CACHE.parent.mkdir(parents=True, exist_ok=True)

    auth = SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        # The redirect URI must match the one configured in your
        # Spotify developer dashboard. localhost is fine for a
        # one-time auth on the same machine that hosts the browser.
        redirect_uri="http://localhost:8888/callback",
        scope=SPOTIFY_SCOPES,
        cache_path=str(TOKEN_CACHE),
        open_browser=False,
    )

    # Bootstrap from the refresh token in .env if the cache is empty
    # (e.g. fresh deploy on the Pi).
    if refresh_token and not TOKEN_CACHE.exists():
        token_info = auth.refresh_access_token(refresh_token)
        auth._save_token_info(token_info)  # type: ignore[attr-defined]

    _cached_client = spotipy.Spotify(auth_manager=auth)
    return _cached_client


def call(fn, *args, **kwargs) -> dict:
    """Run a Spotify API call, translating exceptions into a friendly
    error dict. Returns ``{"ok": True, "data": ...}`` on success and
    ``{"error": "..."}`` otherwise."""
    try:
        client = get_client()
    except NotConfigured as e:
        return {"error": "spotify not configured", "detail": str(e)}

    try:
        data = fn(client, *args, **kwargs)
    except Exception as e:  # noqa: BLE001 — surface to model
        return {"error": "spotify call failed", "detail": repr(e)}

    return {"ok": True, "data": data}
