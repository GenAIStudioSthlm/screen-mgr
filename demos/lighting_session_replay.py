#!/usr/bin/env python3
"""Phase 1 (Lighting MCP) — video-script replay.

Plays out as a scripted video re-enactment of the planning → build →
proof arc for the Lighting MCP, with clear DAN: / CLAUDE: speaker
labels, scene headers, and stage directions. Designed for demo
recordings and screen-share walk-throughs, NOT part of the screen-mgr
platform.

Run it in a terminal:
    python demos/lighting_session_replay.py

~80 s of paced playback. Ctrl-C aborts cleanly.

Color choices:
    Claude  = Anthropic orange (closest ANSI-256 slot: 173 ≈ #d7875f)
    Dan     = warm cream (230 ≈ #ffffd7)
    Scene headers / actions = warm tan
    Stage directions        = dim grey, italic-feel
"""

from __future__ import annotations

import sys
import time


# UTF-8 stdout so Windows cp1252 doesn't choke on em-dashes / box-drawing / °.
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------------- styling

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
ITALIC = "\033[3m"

# Anthropic-brand-ish palette in ANSI 256.
CLAUDE_COLOR = "\033[38;5;173m"   # warm orange ≈ #d7875f
DAN_COLOR = "\033[38;5;230m"      # warm cream ≈ #ffffd7
SCENE_COLOR = "\033[38;5;215m"    # warm tan for scene headers
STAGE_COLOR = "\033[38;5;243m"    # dim grey for stage directions
OUTPUT_COLOR = "\033[38;5;245m"   # mock terminal output
TOOL_COLOR = "\033[38;5;215m"     # tool / action lines
OK_COLOR = "\033[38;5;120m"       # checkmark green
TITLE_COLOR = "\033[38;5;173m"    # title card uses Claude's orange

WIDTH = 72


# ---------------------------------------------------------------------- pacing


def _type(text: str, color: str = "", delay: float = 0.018, end: str = "\n") -> None:
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
    """Instant print — long output blocks where typewriter is annoying."""
    sys.stdout.write(text + end)
    sys.stdout.flush()


def _pause(seconds: float) -> None:
    time.sleep(seconds)


def dan(text: str) -> None:
    sys.stdout.write(f"{DAN_COLOR}{BOLD}DAN:{RESET}    ")
    # Indent continuation if the line wraps in the script source.
    _type(text, color=DAN_COLOR, delay=0.018)
    _pause(0.55)


def claude(text: str, delay: float = 0.016) -> None:
    sys.stdout.write(f"{CLAUDE_COLOR}{BOLD}CLAUDE:{RESET} ")
    _type(text, color=CLAUDE_COLOR, delay=delay)
    _pause(0.45)


def claude_more(text: str) -> None:
    """Continuation line for Claude (no speaker label, indented)."""
    sys.stdout.write("        ")
    _type(text, color=CLAUDE_COLOR, delay=0.014)
    _pause(0.15)


def stage(text: str) -> None:
    _say(f"        {STAGE_COLOR}{ITALIC}[{text}]{RESET}")
    _pause(0.3)


def action(text: str, ok: bool = True) -> None:
    mark = f"{OK_COLOR}✓{RESET}" if ok else f"{STAGE_COLOR}…{RESET}"
    _say(f"        {mark} {DIM}{text}{RESET}")
    _pause(0.22)


def scene(number: int, title: str) -> None:
    _say("")
    _say(f"{SCENE_COLOR}{'─' * WIDTH}{RESET}")
    _say(f"{SCENE_COLOR}{BOLD}  SCENE {number} — {title.upper()}{RESET}")
    _say(f"{SCENE_COLOR}{'─' * WIDTH}{RESET}")
    _say("")
    _pause(0.5)


def title_card(lines: list[str]) -> None:
    _say("")
    top = "┌" + "─" * (WIDTH - 2) + "┐"
    bot = "└" + "─" * (WIDTH - 2) + "┘"
    _say(f"{TITLE_COLOR}{top}{RESET}")
    for line in lines:
        padded = line.center(WIDTH - 4)
        _say(f"{TITLE_COLOR}│ {BOLD}{padded}{RESET}{TITLE_COLOR} │{RESET}")
    _say(f"{TITLE_COLOR}{bot}{RESET}")
    _say("")
    _pause(1.2)


def code(lines: list[str], lang: str = "python") -> None:
    _say(f"{DIM}        ┌─ {lang}{RESET}")
    for line in lines:
        _say(f"{DIM}        │ {line}{RESET}")
        time.sleep(0.045)
    _say(f"{DIM}        └─{RESET}")
    _pause(0.35)


def output(lines: list[str]) -> None:
    for line in lines:
        _say(f"{OUTPUT_COLOR}        {line}{RESET}")
        time.sleep(0.13 if ("frame" in line or ">>>" in line) else 0.06)
    _pause(0.45)


def fade() -> None:
    """Brief beat between scenes."""
    _pause(0.6)


# ---------------------------------------------------------------------- script


def main() -> int:
    # ─────────────────────────────────────────────────────────────────
    # OPENING TITLE
    # ─────────────────────────────────────────────────────────────────
    title_card([
        "STUDIO  MCP  —  EPISODE  1",
        "",
        "Phase 1: Lighting MCP, plan to proof",
        "",
        "Dan Gemvall × Claude · GenAI Studio Stockholm",
    ])
    stage("Fade in. A laptop screen. A Raspberry Pi blinks on the desk.")
    fade()

    # ─────────────────────────────────────────────────────────────────
    scene(1, "The pitch")
    # ─────────────────────────────────────────────────────────────────

    dan(
        "I want to make the studio agentic. Let's plan 3 MCP servers — "
        "Lighting, Screens, LED — plus specialists and a Studio "
        "orchestrator. Start with Lighting because it's the easiest "
        "to prove."
    )

    claude("Good arc. Here's the architecture I'd propose:")
    claude_more("• In-process FastMCP servers mounted at /mcp/<domain>/sse")
    claude_more("• Each wraps an existing Python manager directly — no HTTP back through /api/*")
    claude_more("• One specialist subagent per MCP, each with its own skills/ dir")
    claude_more("• Studio orchestrator owns the operator chat; delegates to specialists")
    _pause(0.5)

    claude("Writing it up.")
    stage("Cut to terminal. Files appear in the project tree.")
    action("TASKS/PLAN_AGENTIC.md — architecture + phases 1-9")
    action("git commit: 'Plan agentic structure — 3 MCP servers + specialists + Studio orchestrator'")
    fade()

    # ─────────────────────────────────────────────────────────────────
    scene(2, "Building the Lighting MCP")
    # ─────────────────────────────────────────────────────────────────

    dan("Go. Build Phase 1. In-process, wraps the Hue Bridge directly.")

    claude(
        "On it. The Lighting MCP wraps modules.hue.client.HueClient — no "
        "HTTP roundtrip back through /api/modules/hue/*, one less hop. "
        "Nine tools to start."
    )
    stage("Code appears on screen.")

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

    action("mcps/lighting/{__init__.py, server.py} created")
    action("main.py: app.mount('/mcp/lighting', server.sse_app())")
    action("requirements.txt: + mcp>=1.2.0")
    fade()

    # ─────────────────────────────────────────────────────────────────
    scene(3, "Deploy + smoke test")
    # ─────────────────────────────────────────────────────────────────

    dan("Push to the Pi and confirm it actually talks to the Hue bridge.")

    claude("Pushing now.")
    action("scp mcps/lighting/server.py → admin@192.168.2.65:/home/admin/screen-mgr/...")
    action("uvicorn --reload picks up the new mount automatically")

    claude("Running an MCP client smoke test from the Pi itself.")
    stage("A second terminal opens, SSHing into studiopi.")
    _say(f"        {TOOL_COLOR}→ ssh admin@studiopi 'python3 -c \"<MCP SSE client>\"'{RESET}")
    _pause(1.0)

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

    claude(
        "Bridge is reachable. Nine tools register. Studio room — group 81 — "
        "has 13 lights. Maker — group 2 — has four. Phase 1 wiring works "
        "end-to-end."
    )
    fade()

    # ─────────────────────────────────────────────────────────────────
    scene(4, "Visible proof — rainbow + intensity")
    # ─────────────────────────────────────────────────────────────────

    dan(
        "Add a startup self-test. Something visible. Rainbow across all "
        "13 Studio lights, then an intensity sweep, settle to a usable "
        "state."
    )

    claude(
        "Building as both an MCP tool and a CLI. Shared logic in "
        "startup_test.py; calls HueClient through asyncio.to_thread so it "
        "doesn't block the event loop."
    )

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
    action("mcps/lighting/startup_test.py + scripts/lights_startup_test.py")
    action("MCP tool: run_startup_test")
    fade()

    dan("Run it.")
    claude("Firing on studiopi. Watch the studio lights.")
    stage("Camera pans to the studio ceiling. 13 Hue bulbs.")
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

    stage("The studio lights settle into a warm 3000 K glow.")
    claude(
        "Rainbow rotated full cycle in roughly five seconds. Intensity sweep "
        "finished at 80 %. Settled to 60 % warm white. Phase 1 is proven "
        "end-to-end."
    )
    fade()

    # ─────────────────────────────────────────────────────────────────
    scene(5, "Closing card")
    # ─────────────────────────────────────────────────────────────────

    _say(f"        {BOLD}{OK_COLOR}✓{RESET}{BOLD} /mcp/lighting/sse — 10 tools, real Hue control{RESET}")
    _say(f"        {BOLD}{OK_COLOR}✓{RESET}{BOLD} run_startup_test — visible self-test (~12 s){RESET}")
    _say(f"        {BOLD}{OK_COLOR}✓{RESET}{BOLD} git commit: 'Phase 1 — Lighting MCP server (in-process)'{RESET}")
    _say("")
    stage(
        "Next episode — Phase 2: the Lighting specialist subagent. "
        "Code lands; end-to-end test blocks on the .env API key on the Pi."
    )
    _say("")

    title_card([
        "END OF EPISODE 1",
        "",
        "PHASE 1 COMPLETE",
    ])

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.stdout.write(RESET + "\n[interrupted]\n")
        sys.stdout.flush()
        sys.exit(130)
