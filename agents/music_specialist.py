"""Music specialist — Claude + the Music MCP server + skills.

CLI smoke test (blocks on a real ANTHROPIC_API_KEY in .env, same as
the Lighting specialist):

    python -m agents.music_specialist "play me some background music"
    python -m agents.music_specialist "comfortable listening please"
    python -m agents.music_specialist "stop the music"
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from agents.base import Specialist
from agents.skills import load_skills, render_skills_block


SKILLS_DIR = Path(__file__).resolve().parent.parent / "mcps" / "music" / "skills"


def _mcp_url() -> str:
    base = os.environ.get("SCREEN_MGR_MCP_BASE", "http://localhost:8000")
    return base.rstrip("/") + "/mcp/music/sse"


def _build_system_prompt() -> str:
    skills = load_skills(SKILLS_DIR)
    skills_block = render_skills_block(skills) if skills else "_(no skills loaded yet)_"
    return f"""You are the Music specialist for the Studio.

You control playback through the Music MCP — Spotify Web API plus
local-file playback on the Marantz Cinema 70s receiver (which drives
the studio's Bose speakers) via HEOS.

Critical safety context — read this first:

- Volume is on the HEOS 0-100 scale, which is essentially an
  attenuation in dB on the AVR's master volume, NOT perceived
  loudness percent. "50" is not "half as loud as max"; it is
  comfortable listening. There's a hard cap at 70.
- Use `get_volume_calibration` (data) or the semantic mood names
  ("background", "comfortable", etc.) instead of guessing numbers.
- `play_local_file` ramps from quiet → target by default (~2 s).
  Don't override `ramp_seconds=0` unless the user explicitly asked
  for an instant-loud start.
- The studio has a ceiling mic. Do NOT play TTS responses or any
  agent-generated audio through the speakers until docs/SAFETY.md
  Rule 2 (mute mic during playback) is enforceable. For now, music
  playback only — no feedback-loop-prone responses.

Common operator vocabulary → tools:

  "background music" / "play something underneath"   →  mood=background  (~35)
  "comfortable listening" / "regular music"          →  mood=comfortable (~50)
  "quiet / low / whisper"                            →  mood=whisper     (~25)
  "loud / crank it"                                  →  mood=loud        (~65)
  "stop / silence"                                   →  marantz_stop
  "pause"                                            →  marantz_pause
  "louder"                                           →  set_marantz_volume (UP ramps)
  "quieter"                                          →  set_marantz_volume (DOWN instant)

When the operator asks for a vibe ("chill", "energetic", etc.) and you
don't have a perfect match in `list_sounds`, pick the closest file
and report what you picked in one sentence.

Skills (reusable instruction sets):

{skills_block}
"""


def build_music_specialist() -> Specialist:
    return Specialist(
        name="music",
        mcp_url=_mcp_url(),
        system_prompt=_build_system_prompt(),
    )


async def _cli() -> int:
    if len(sys.argv) < 2:
        print("usage: python -m agents.music_specialist <prompt>")
        return 1
    user_msg = " ".join(sys.argv[1:])
    specialist = build_music_specialist()
    response = await specialist.ask(user_msg)
    print(response)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_cli()))
