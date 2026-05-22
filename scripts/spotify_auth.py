"""One-time Spotify OAuth helper for the Music MCP.

Run this **on a dev machine with a browser** (not the headless Pi).
Walks the OAuth Authorization-Code flow once and prints the refresh
token. Copy that token into the Pi's `.env` as `SPOTIFY_REFRESH_TOKEN`
and the Music MCP will work after the next uvicorn reload.

Setup checklist before running:

  1. Create a Spotify Developer app at https://developer.spotify.com/dashboard
  2. Add redirect URI `http://localhost:8888/callback` in the app settings.
  3. Note the Client ID + Client Secret.
  4. Run this script with those in your shell environment:

       export SPOTIFY_CLIENT_ID=...
       export SPOTIFY_CLIENT_SECRET=...
       python scripts/spotify_auth.py

  5. The script opens your browser to Spotify's consent page.
     Approve, and it'll print the refresh token.
  6. SSH to the Pi and add three lines to /home/admin/screen-mgr/.env:
       SPOTIFY_CLIENT_ID=...
       SPOTIFY_CLIENT_SECRET=...
       SPOTIFY_REFRESH_TOKEN=<from step 5>

The Music MCP picks these up on the next uvicorn reload (`systemctl
restart screen-mgr` on the Pi if reload is off).
"""

from __future__ import annotations

import os
import sys


SCOPES = (
    "user-read-playback-state "
    "user-modify-playback-state "
    "user-read-currently-playing"
)


def main() -> int:
    client_id = os.environ.get("SPOTIFY_CLIENT_ID", "").strip()
    client_secret = os.environ.get("SPOTIFY_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        print(
            "error: set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET in your "
            "shell before running. See module docstring."
        )
        return 1

    try:
        from spotipy.oauth2 import SpotifyOAuth  # type: ignore
    except ImportError:
        print("error: spotipy not installed. Run `pip install spotipy` first.")
        return 1

    auth = SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri="http://localhost:8888/callback",
        scope=SCOPES,
        cache_path=".spotify-token-cache",  # local, gitignored
        open_browser=True,
    )

    print("Opening your browser to Spotify's consent page …")
    token_info = auth.get_access_token(as_dict=True)
    if not isinstance(token_info, dict) or "refresh_token" not in token_info:
        print("error: did not receive a refresh token. Try again.")
        return 1

    print("\nSUCCESS. Copy this refresh token into the Pi's .env "
          "as SPOTIFY_REFRESH_TOKEN:\n")
    print(token_info["refresh_token"])
    print(
        "\nNext: SSH to studiopi and add to /home/admin/screen-mgr/.env "
        "(alongside ANTHROPIC_API_KEY):"
    )
    print(f"  SPOTIFY_CLIENT_ID={client_id}")
    print("  SPOTIFY_CLIENT_SECRET=<your secret>")
    print("  SPOTIFY_REFRESH_TOKEN=<the refresh token above>")
    return 0


if __name__ == "__main__":
    sys.exit(main())
