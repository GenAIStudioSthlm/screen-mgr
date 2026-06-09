"""Serve the Braccio FastMCP over localhost SSE.

The handoff ships a stdio server (server.py), but the studio's Claude
Code runs under an org policy that blocks stdio MCP servers while
allowing `http://localhost*` ones. So we expose the very same FastMCP
instance over SSE on localhost — no change to the tools or arm logic.

Runs in THIS package's own venv (kept separate from the main app so the
heavy vision deps can land here later without touching screen-mgr).

    BRACCIO_SSE_HOST  (default 127.0.0.1)
    BRACCIO_SSE_PORT  (default 8011)
"""

import os

# server.py inserts its own dir on sys.path and defines `mcp` (the FastMCP
# instance with all the arm/vision tools). Importing it does NOT connect to
# the arm — that only happens when a tool runs.
from server import mcp

if __name__ == "__main__":
    mcp.settings.host = os.environ.get("BRACCIO_SSE_HOST", "127.0.0.1")
    mcp.settings.port = int(os.environ.get("BRACCIO_SSE_PORT", "8011"))
    mcp.run(transport="sse")
