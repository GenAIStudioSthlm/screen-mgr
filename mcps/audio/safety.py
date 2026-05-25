"""Audio-output safety rails.

The studio has a ceiling mic (Sennheiser TCC M S W) and a high-output
amp + speaker chain (Marantz Cinema 70s + room speakers). Any closed
loop between them — mic → STT → orchestrator → TTS / music → speakers
→ mic — risks acoustic feedback that builds rapidly enough to damage
the speakers.

This module centralises the **safe maximum output volume** every
audio-write code path must honour. Today we enforce a single cap;
future work (see docs/SAFETY.md) adds auto-mute-mic-during-playback,
loop detection, and half-duplex policy on top of this.

Override the cap by setting `MAX_OUTPUT_VOLUME_PCT` in the Pi's
`.env`. Don't raise it without thinking through the feedback model
first.
"""

from __future__ import annotations

import os
from typing import Optional


# Reasonable conservative default. The studio's Marantz at 70 % is
# loud enough for any presentation; raise only after testing with the
# specific room + speakers + mic positioning.
DEFAULT_MAX_OUTPUT_VOLUME_PCT = 70


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
