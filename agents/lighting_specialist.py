"""Lighting specialist — Claude + the Lighting MCP server + skills.

CLI smoke test:
    python -m agents.lighting_specialist "what's the current state of the Maker room"
    python -m agents.lighting_specialist "set the studio to presentation mode"
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from agents.base import Specialist
from agents.skills import load_skills, render_skills_block


SKILLS_DIR = Path(__file__).resolve().parent.parent / "mcps" / "lighting" / "skills"


def _mcp_url() -> str:
    base = os.environ.get("SCREEN_MGR_MCP_BASE", "http://localhost:8000")
    return base.rstrip("/") + "/mcp/lighting/sse"


def _build_system_prompt() -> str:
    skills = load_skills(SKILLS_DIR)
    skills_block = render_skills_block(skills) if skills else "_(no skills loaded yet)_"
    return f"""You are the Lighting specialist for the Studio.

You control the Philips Hue Bridge via MCP tools. Your job is to translate
user requests into the right sequence of tool calls and report back
concisely (one or two sentences). You don't narrate every tool call.

Guidelines:
- Use `list_groups` to find rooms by name (typically "Studio" and "Maker").
- Prefer `recall_scene` when a named bridge scene fits the request — it's
  one round-trip and applies the user's pre-tuned per-light state.
- Prefer `set_group` over fanning out per-light writes when the change
  applies to a whole room.
- After making changes, give the user a single-line confirmation.
- If a request is ambiguous (which room? how bright?), ask one
  clarifying question rather than guessing.
- If a tool returns an error, report what failed instead of retrying
  blindly.

Skills (reusable instruction sets for common requests):

{skills_block}
"""


def build_lighting_specialist() -> Specialist:
    return Specialist(
        name="lighting",
        mcp_url=_mcp_url(),
        system_prompt=_build_system_prompt(),
    )


async def _cli() -> int:
    if len(sys.argv) < 2:
        print("usage: python -m agents.lighting_specialist <prompt>")
        return 1
    user_msg = " ".join(sys.argv[1:])
    specialist = build_lighting_specialist()
    response = await specialist.ask(user_msg)
    print(response)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_cli()))
