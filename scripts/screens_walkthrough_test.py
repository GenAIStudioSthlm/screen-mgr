"""Thin CLI wrapper that invokes the Screens MCP's
`run_content_walkthrough` tool — cycles a target screen through every
content type so we can see they all render.

Takes ~24 seconds end-to-end (6 states × 4s).

Usage on the Pi:
    cd /home/admin/screen-mgr && source venv/bin/activate
    python scripts/screens_walkthrough_test.py [screen_id]
"""

import asyncio
import json
import os
import sys

from mcp.client.session import ClientSession
from mcp.client.sse import sse_client


async def main() -> int:
    base = os.environ.get("SCREEN_MGR_MCP_BASE", "http://localhost:8000")
    url = base.rstrip("/") + "/mcp/screens/sse"
    args: dict = {}
    if len(sys.argv) > 1:
        try:
            args["screen_id"] = int(sys.argv[1])
        except ValueError:
            print(f"usage: {sys.argv[0]} [screen_id]")
            return 1

    print(f"[walkthrough] connecting to {url}", flush=True)
    async with sse_client(url) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("[walkthrough] calling run_content_walkthrough ...", flush=True)
            result = await session.call_tool("run_content_walkthrough", args)
            text = result.content[0].text if result.content else "(no content)"
            try:
                print(json.dumps(json.loads(text), indent=2))
            except Exception:
                print(text)
            if getattr(result, "isError", False):
                return 1

    print("\n[walkthrough] done")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
