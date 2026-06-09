"""Thin CLI wrapper for the Music MCP `run_speaker_test` tool.

Plays a full-spectrum reference track on a named Spotify Connect
device at a fixed volume, then pauses. Default: Hotel California
(Eagles) on the studio's Bose speakers at 20% for 20 seconds.

Won't actually make sound until Spotify is configured on the Pi
(see docs/DEPLOY.md → Spotify). Until then this returns the
"spotify not configured" error from the Music MCP.

Usage on the Pi:
    python scripts/music_speaker_test.py
    python scripts/music_speaker_test.py --device "Living Room"
    python scripts/music_speaker_test.py --track "So What Miles Davis" --volume 30 --seconds 30
"""

import argparse
import asyncio
import json
import os
import sys

from mcp.client.session import ClientSession
from mcp.client.sse import sse_client


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", default="bose")
    ap.add_argument("--track", default="Hotel California Eagles")
    ap.add_argument("--volume", type=int, default=20)
    ap.add_argument("--seconds", type=int, default=20)
    args = ap.parse_args()

    base = os.environ.get("SCREEN_MGR_MCP_BASE", "http://localhost:8000")
    url = base.rstrip("/") + "/mcp/music/sse"

    print(f"[speaker-test] connecting to {url}", flush=True)
    async with sse_client(url) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("[speaker-test] calling run_speaker_test …", flush=True)
            result = await session.call_tool(
                "run_speaker_test",
                {
                    "device_query": args.device,
                    "volume_pct": args.volume,
                    "track_query": args.track,
                    "play_seconds": args.seconds,
                },
            )
            text = result.content[0].text if result.content else "(no content)"
            try:
                print(json.dumps(json.loads(text), indent=2))
            except Exception:
                print(text)
            if getattr(result, "isError", False):
                return 1

    print("\n[speaker-test] done")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
