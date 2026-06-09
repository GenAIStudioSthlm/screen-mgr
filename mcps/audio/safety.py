"""Audio-output safety rails.

The studio has a ceiling mic (Sennheiser TCC M S W) and a high-output
amp + speaker chain (Marantz Cinema 70s + room speakers). Any closed
loop between them — mic → STT → orchestrator → TTS / music → speakers
→ mic — risks acoustic feedback that builds rapidly enough to damage
the speakers.

This module centralises:
  - the **hard maximum output volume** every audio-write code path
    must honour (`cap_volume`)
  - the **semantic volume vocabulary** an agent uses to pick a sensible
    level for a mood (`volume_for_mood`)
  - the **calibration table** so anyone (agent or human) reading the
    docstrings learns what numbers actually sound like

Today we enforce the cap and document the vocabulary; future work (see
docs/SAFETY.md) adds auto-mute-mic-during-playback, loop detection, and
half-duplex policy on top.

Override the cap by setting `MAX_OUTPUT_VOLUME_PCT` in the Pi's `.env`.
Don't raise it without re-reading docs/SAFETY.md.
"""

from __future__ import annotations

import os
from typing import Optional


# Reasonable conservative default. The studio's Marantz at 70 is
# loud enough for any presentation; raise only after testing with the
# specific room + speakers + mic positioning.
DEFAULT_MAX_OUTPUT_VOLUME_PCT = 70


# ---------------------------------------------------------------------- calibration

# Calibrated on the studio's Marantz Cinema 70s + Bose chain (2026-05-25).
# HEOS volume 0-100 maps onto the AVR's master volume in dB — it is NOT
# perceived loudness percent. "50" is not "half as loud as max"; it is
# the dB level that feels like "comfortable listening" on this setup.
#
# Agents reading this table via list_tools should use these as semantic
# anchors: "background music" → ~30, "loud party" → ~65 (capped at 70).

VOLUME_CALIBRATION: dict[int, str] = {
    10: "inaudible — silent for practical purposes",
    25: "whisper / very low — confirms playback works but you have to listen for it",
    35: "background — music underneath conversation, easy to talk over",
    50: "comfortable / regular listening — what you'd pick to actually listen",
    65: "loud — focus-the-room level, near max",
    70: "HARD CAP — refused above this without raising MAX_OUTPUT_VOLUME_PCT",
}


# Named moods → recommended level. The agent calls volume_for_mood("background")
# instead of inventing a number; we promise the result will be both sensible
# and safe (always at or below the cap).
SEMANTIC_VOLUMES: dict[str, int] = {
    "inaudible": 10,
    "whisper": 25,
    "background": 35,
    "comfortable": 50,
    "loud": 65,
    "max": 70,
}


def volume_for_mood(mood: str) -> int:
    """Map a semantic mood to a safe HEOS volume level.

    Unknown moods → ``SAFE_TEST_VOLUME_PCT`` (whisper-low) so the
    fail-safe is "quiet but audible" rather than a guess at loud."""
    key = (mood or "").strip().lower()
    if key in SEMANTIC_VOLUMES:
        return SEMANTIC_VOLUMES[key]
    return SAFE_TEST_VOLUME_PCT


# Starting point for any "test" or first-time playback operation.
# Whisper-low: audible enough to confirm sound is reaching the speakers,
# quiet enough that a surprise doesn't damage anyone's ears.
SAFE_TEST_VOLUME_PCT = 25


def max_output_volume_pct() -> int:
    """Current hard ceiling. Re-read from env on every call so an
    operator can adjust .env without restarting the service (uvicorn
    --reload picks it up too)."""
    raw = os.environ.get("MAX_OUTPUT_VOLUME_PCT", "").strip()
    if not raw:
        return DEFAULT_MAX_OUTPUT_VOLUME_PCT
    try:
        v = int(raw)
    except ValueError:
        return DEFAULT_MAX_OUTPUT_VOLUME_PCT
    return max(0, min(100, v))


def cap_volume(requested_pct: Optional[int]) -> tuple[int, bool]:
    """Clamp a requested volume to the safety ceiling.

    Returns (effective_pct, was_capped). `was_capped=True` means the
    caller asked for more than the policy allows; consumers should
    surface that to the operator so they know the asked-for value
    didn't fully land.

    None / negative / non-int inputs are coerced to 0 to fail safe.
    """
    ceiling = max_output_volume_pct()
    if requested_pct is None:
        return (0, False)
    try:
        req = int(requested_pct)
    except (TypeError, ValueError):
        return (0, False)
    req = max(0, req)
    if req > ceiling:
        return (ceiling, True)
    return (req, False)
