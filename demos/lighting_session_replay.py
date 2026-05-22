#!/usr/bin/env python3
"""Phase 1 (Lighting MCP) session replay.

A scripted, paced re-telling of the planning + build + proof arc for
the Lighting MCP server. Plays out in the terminal as a fake
conversation — meant for demos / handoffs / recordings, NOT part of
the screen-mgr platform.

Usage:
    python demos/lighting_session_replay.py

Stop early with Ctrl-C. ~70 s of playback at default pace.

No external deps — ANSI colors only. Works in any modern terminal
(Windows Terminal, iTerm2, gnome-terminal, etc).
"""

from __future__ import annotations

import sys
import time


# Force UTF-8 on Windows terminals (cp1252 chokes on box-drawing chars and em-dashes).
# Python 3.7+ exposes stdout.reconfigure; older versions just keep going.
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001 — best effort, don't crash
        pass


# ---------------------------------------------------------------------- styling

RESET = "\033[0m"
DIM = "\033[2m"
BOLD = "\033[1m"

USER_COLOR = "\033[38;5;81m"        # cyan-ish
ASSISTANT_COLOR = "\033[38;5;156m"  # mint
TOOL_COLOR = "\033[38;5;221m"       # warm yellow
OUTPUT_COLOR = "\033[38;5;245m"     # light grey
HEADER_COLOR = "\033[38;5;213m"     # pink/magenta
OK_COLOR = "\033[38;5;120m"         # green
WARN_COLOR = "\033[38;5;215m"


# ---------------------------------------------------------------------- pacing


def _type(text: str, color: str = "", delay: float = 0.018, end: str = "\n") -> None:
    """Character-by-character print with a tiny extra dwell on punctuation
    so the line lands naturally."""
    if color:
        sys.stdout.write(color)
    for ch in text:
        sys.stdout.write(ch)
        sys.stdout.flush()
        if ch in ",.;:!?":
            time.sleep(delay * 4)
        elif ch == " ":
            time.sleep(delay * 0.6)
        else:
            time.sleep(delay)
    if color:
        sys.stdout.write(RESET)
    sys.stdout.write(end)
    sys.stdout.flush()


def _say(text: str, end: str = "\n") -> None:
    """Instant print — for long output blocks where typewriter is annoying."""
    sys.stdout.write(text + end)
    sys.stdout.flush()


def _pause(seconds: float) -> None:
    time.sleep(seconds)


def user(text: str) -> None:
    sys.stdout.write(f"{USER_COLOR}{BOLD}you ›{RESET} ")
    _type(text, color=USER_COLOR, delay=0.018)
    _pause(0.55)


def assistant(text: str, delay: float = 0.014) -> None:
    sys.stdout.write(f"{ASSISTANT_COLOR}{BOLD}claude ●{RESET} ")
    _type(text, color=ASSISTANT_COLOR, delay=delay)
    _pause(0.4)


def tool(text: str, ok: bool = True) -> None:
    mark = f"{OK_COLOR}✓{RESET}" if ok else f"{WARN_COLOR}…{RESET}"
    _say(f"        {mark} {DIM}{text}{RESET}")
    _pause(0.22)


def heading(text: str) -> None:
    _say("")
    _say(f"{HEADER_COLOR}{BOLD}── {text} ──{RESET}")
    _say("")
    _pause(0.3)


def code(lines: list[str], lang: str = "python") -> None:
    _say(f"{DIM}        ┌─ {lang}{RESET}")
    for line in lines:
        _say(f"{DIM}        │ {line}{RESET}")
        time.sleep(0.045)
    _say(f"{DIM}        └─{RESET}")
    _pause(0.35)


def output(lines: list[str]) -> None:
    """Mock terminal output — printed fast, dimmed."""
    for line in lines:
        _say(f"{OUTPUT_COLOR}        {line}{RESET}")
        # Slow down on "frame" / ">>>" so the eye catches the progression.
        time.sleep(0.13 if ("frame" in line or ">>>" in line) else 0.06)
    _pause(0.45)


# ---------------------------------------------------------------------- script


def main() -> int:
    heading("Studio agentic plan — Phase 1: Lighting MCP")
    _pause(0.4)

    user(
        "I want to make the studio agentic. Let's plan 3 MCP servers — "
        "Lighting, Screens, LED — plus specialists and a Studio orchestrator. "
        "Start with Lighting because it's the easiest to prove."
    )

    assistant("Good arc. The architecture I'd propose:")
    _say(f"        {ASSISTANT_COLOR}• In-process FastMCP servers mounted at {DIM}/mcp/<domain>/sse{RESET}")
    _say(f"        {ASSISTANT_COLOR}• Each wraps an existing Python manager directly — no HTTP back through /api/*{RESET}")
    _say(f"        {ASSISTANT_COLOR}• One specialist subagent per MCP, each with its own skills/ dir{RESET}")
    _say(f"        {ASSISTANT_COLOR}• Studio orchestrator owns the operator chat; delegates to specialists{RESET}")
    _pause(0.55)

    assistant("Writing it all up.")
    tool("TASKS/PLAN_AGENTIC.md — architecture + phases 1-9")
    tool("git commit: 'Plan agentic structure — 3 MCP servers + specialists + Studio orchestrator'")
    _pause(0.5)

    heading("Phase 1 — Building the Lighting MCP")

    user("Go. Build Phase 1. In-process, wraps the Hue Bridge directly.")

    assistant(
        "On it. The Lighting MCP wraps modules.hue.client.HueClient — no HTTP "
        "roundtrip back through /api/modules/hue/*, one less hop. 9 tools to start."
    )
    _pause(0.3)

    code([
        "# mcps/lighting/server.py",
        "from mcp.server.fastmcp import FastMCP",
        "from modules import registry",
        "from modules.hue.client import HueClient",
        "",
        "server = FastMCP('lighting')",
        "",
        "@server.tool()",
        "def list_lights() -> dict:",
        "    return _client().get_lights()",
        "",
        "@server.tool()",
        "def set_group(group_id: str, on=None, brightness_pct=None,",
        "              color_hex=None, kelvin=None) -> dict:",
        "    return _client().set_group(group_id, _build_state(...))",
        "",
        "# ... 9 tools total: list_lights, list_groups, list_scenes,",
        "#     get_bridge_status, set_light, set_group, recall_scene,",
        "#     all_on, all_off",
    ])

    tool("mcps/lighting/{__init__.py, server.py} created")
    tool("main.py: app.mount('/mcp/lighting', server.sse_app())")
    tool("requirements.txt: + mcp>=1.2.0")
    _pause(0.4)

    heading("Deploy + smoke-test on studiopi")

    user("Push to the Pi and confirm it actually talks to the Hue bridge.")

    assistant("Pushing now.")
    tool("scp mcps/lighting/server.py → admin@192.168.2.65:/home/admin/screen-mgr/...")
    tool("uvicorn --reload picks up the new mount automatically")
    _pause(0.4)

    assistant("Running an MCP client smoke test from the Pi itself.")
    _say(f"        {TOOL_COLOR}→ ssh admin@studiopi 'python3 -c \"<MCP SSE client>\"'{RESET}")
    _pause(0.9)

    output([
        "[smoke] connecting to http://localhost:8000/mcp/lighting/sse",
        "[smoke] tools: ['list_lights', 'list_groups', 'list_scenes',",
        "                'get_bridge_status', 'set_light', 'set_group',",
        "                'recall_scene', 'all_on', 'all_off']",
        "[smoke] list_groups → {",
        '          "2":  {"name": "Maker",  "lights": ["7","8","5","9"], ...},',
        '          "81": {"name": "Studio", "lights": [13 lights],       ...}',
        "        }",
    ])

    assistant(
        "Bridge is reachable, 9 tools register, Studio room (group 81) has 13 lights, "
        "Maker (group 2) has 4. Phase 1 wiring works end-to-end."
    )
    _pause(0.5)

    heading("Visible self-test: rainbow + intensity sweep")

    user(
        "Add a startup self-test — something visible. Rainbow across all 13 Studio "
        "lights, then an intensity sweep, settle to a usable state."
    )

    assistant(
        "Building as both an MCP tool and a CLI. Shared logic in startup_test.py; "
        "calls HueClient through asyncio.to_thread so it doesn't block the event loop."
    )
    _pause(0.3)

    code([
        "# Rainbow phase — each light starts at a different hue, then rotates",
        "for frame in range(6):",
        "    for i, light_id in enumerate(lights):           # 13 lights",
        "        hue_deg = (i * 27.7 + frame * 60) % 360",
        "        client.set_light(light_id, {",
        "            'on': True, 'bri': 203, 'xy': hsv_xy(hue_deg)",
        "        })",
        "        await asyncio.sleep(0.04)                   # under Hue rate cap",
        "",
        "# Intensity phase — 10 / 80 / 40 / 80 %",
        "for pct in [10, 80, 40, 80]:",
        "    client.set_group('81', {'bri': pct_to_bri(pct), 'on': True})",
        "    await asyncio.sleep(1.25)",
        "",
        "# Settle — 60 % at 3000 K warm white, room left usable",
        "client.set_group('81', {'bri': 152, 'ct': 333, 'on': True})",
    ])
    tool("mcps/lighting/startup_test.py + scripts/lights_startup_test.py")
    tool("MCP tool: run_startup_test")
    _pause(0.4)

    user("Run it.")

    assistant("Firing on studiopi. Watch the studio lights.")
    _say(f"        {TOOL_COLOR}→ curl -X POST http://localhost:8000/api/modules/hue/run_startup_test{RESET}")
    _pause(0.8)

    output([
        "[startup-test] connecting to http://localhost:8000/mcp/lighting/sse",
        "[startup-test] 9 MCP tools available",
        "",
        "=== RAINBOW WALK — 13 lights, 6 frames, ~5s ===",
        "  frame  1/6  base_hue=   0.0°",
        "  frame  2/6  base_hue=  60.0°",
        "  frame  3/6  base_hue= 120.0°",
        "  frame  4/6  base_hue= 180.0°",
        "  frame  5/6  base_hue= 240.0°",
        "  frame  6/6  base_hue= 300.0°",
        "",
        "=== INTENSITY TEST on group 81 (10/80/40/80%) ===",
        "  >>> set_group(brightness_pct=10)    → bri 25/254",
        "  >>> set_group(brightness_pct=80)    → bri 203/254",
        "  >>> set_group(brightness_pct=40)    → bri 102/254",
        "  >>> set_group(brightness_pct=80)    → bri 203/254",
        "",
        "=== SETTLE — set_group(brightness_pct=60, kelvin=3000) ===",
        "",
        "[startup-test] done — room left at 60% / 3000K",
    ])

    assistant(
        "Rainbow rotated full cycle over ~5 s, intensity sweep finished at 80 %, "
        "settled to 60 % warm white. Phase 1 proven end-to-end."
    )
    _pause(0.6)

    heading("Phase 1 done")
    _say(f"        {BOLD}{OK_COLOR}✓{RESET}{BOLD} /mcp/lighting/sse — 10 tools, real Hue control{RESET}")
    _say(f"        {BOLD}{OK_COLOR}✓{RESET}{BOLD} run_startup_test — visible self-test (~12 s){RESET}")
    _say(f"        {BOLD}{OK_COLOR}✓{RESET}{BOLD} git commit: 'Phase 1 — Lighting MCP server (in-process)'{RESET}")
    _say("")
    _say(
        f"        {DIM}Next: Phase 2 — Lighting specialist subagent. Code lands; "
        f"end-to-end test blocks on the .env API key on the Pi.{RESET}"
    )
    _say("")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.stdout.write(RESET + "\n[interrupted]\n")
        sys.stdout.flush()
        sys.exit(130)
