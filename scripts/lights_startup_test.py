"""Thin CLI wrapper that invokes the Lighting MCP's `run_startup_test`
tool. The actual sequence lives in `mcps/lighting/startup_test.py` so
the MCP tool and this script share one source of truth.

Takes ~12 seconds end-to-end (rainbow + intensity + settle).

Usage on the Pi:
    cd /home/admin/screen-mgr && source venv/bin/activate
    python scripts/lights_startup_test.py
"""

import asyncio
import json
import os
import sys

from mcp.client.session import ClientSession
from mcp.client.sse import sse_client


async def main() -> int:
    base = os.environ.get("SCREEN_MGR_MCP_BASE", "http://localhost:8000")
    url = base.rstrip("/") + "/mcp/lighting/sse"
    print(f"[startup-test] connecting to {url}", flush=True)

    async with sse_client(url) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("[startup-test] calling run_startup_test ...", flush=True)
            result = await session.call_tool("run_startup_test", {})
            text = result.content[0].text if result.content else "(no content)"
            try:
                parsed = json.loads(text)
                print(json.dumps(parsed, indent=2))
            except Exception:
                print(text)
            if getattr(result, "isError", False):
                return 1

    print("\n[startup-test] done")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
