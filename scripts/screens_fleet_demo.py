"""Thin CLI wrapper for the Screens MCP `run_fleet_demo` tool —
cycles every available screen through 3 modes (URL web → URL YouTube →
default) and settles the fleet on the AI News scene.

Takes ~17 seconds end-to-end + however long the settle scene takes.

Usage on the Pi:
    cd /home/admin/screen-mgr && source venv/bin/activate
    python scripts/screens_fleet_demo.py
    python scripts/screens_fleet_demo.py 1 2 3   # target specific screen ids
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
            args["target_screen_ids"] = [int(a) for a in sys.argv[1:]]
        except ValueError:
            print(f"usage: {sys.argv[0]} [screen_id ...]")
            return 1

    print(f"[fleet-demo] connecting to {url}", flush=True)
    async with sse_client(url) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("[fleet-demo] calling run_fleet_demo ...", flush=True)
            result = await session.call_tool("run_fleet_demo", args)
            text = result.content[0].text if result.content else "(no content)"
            try:
                print(json.dumps(json.loads(text), indent=2))
            except Exception:
                print(text)
            if getattr(result, "isError", False):
                return 1

    print("\n[fleet-demo] done")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
