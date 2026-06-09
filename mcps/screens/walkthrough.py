"""Screen content walkthrough — drives a target screen through every
major content type as a visible self-test.

Sequence (each state pauses ~4s by default, ~24s total):

  1. picture   — first available image
  2. url       — generic web page (example.com)
  3. url       — YouTube embed (so we exercise iframe/video playback)
  4. pdf       — first available PDF
  5. news      — landscape mode
  6. default   — settle back to the studio logo

States with no available media are skipped (and recorded as such) so
the walkthrough never wedges itself trying to set a picture when the
pictures folder is empty.

Shared between the MCP tool (`run_content_walkthrough` in server.py) and
the CLI script (`scripts/screens_walkthrough_test.py`).
"""

from __future__ import annotations

import asyncio
import os
from typing import Any, Optional

from connections import connection_manager
from screens import screen_manager


PICTURE_FOLDER = "static/pictures"
VIDEO_FOLDER = "static/videos"
PDF_FOLDER = "static/pdfs"

# YouTube embed URL — uses /embed/ so the iframe renders inline cleanly.
# Big Buck Bunny — Creative Commons, safe demo content.
YOUTUBE_EMBED_URL = "https://www.youtube.com/embed/aqz-KE-bpKQ"
GENERIC_URL = "https://example.com"
TEXT_DEMO = "Walkthrough test — text mode"


def _first_file(folder: str, exts: tuple[str, ...]) -> Optional[str]:
    if not os.path.isdir(folder):
        return None
    for name in sorted(os.listdir(folder)):
        full = os.path.join(folder, name)
        if os.path.isfile(full) and name.lower().endswith(exts):
            return name
    return None


def _pick_target(target_screen_id: Optional[int]):
    """Pick the screen we drive. Explicit id wins; else the first
    connected screen; else screen 1."""
    if target_screen_id is not None:
        screen = next((s for s in screen_manager.screens if s.id == target_screen_id), None)
        if screen is None:
            raise KeyError(f"screen_id {target_screen_id} not found")
        return screen
    for s in screen_manager.screens:
        if s.connected:
            return s
    if not screen_manager.screens:
        raise RuntimeError("no screens configured")
    return screen_manager.screens[0]


def _build_sequence() -> list[tuple[str, str, str]]:
    """Build the ordered list of (label, content_type, content_value).

    Each entry is included only if the underlying media (when needed)
    exists on disk — empty-folder cases are skipped at runtime.
    """
    seq: list[tuple[str, str, str]] = []

    picture = _first_file(PICTURE_FOLDER, (".png", ".jpg", ".jpeg", ".gif"))
    if picture:
        seq.append(("picture", "picture", picture))
    else:
        seq.append(("picture (skipped: no files in static/pictures)", "skip", ""))

    seq.append(("url (web page)", "url", GENERIC_URL))
    seq.append(("url (YouTube)", "url", YOUTUBE_EMBED_URL))

    pdf = _first_file(PDF_FOLDER, (".pdf",))
    if pdf:
        seq.append(("pdf", "pdf", pdf))
    else:
        seq.append(("pdf (skipped: no files in static/pdfs)", "skip", ""))

    seq.append(("AI news (landscape)", "news", "landscape"))

    # Settle.
    seq.append(("default (studio logo — settle)", "default", ""))

    return seq


_CONTENT_VALUE_FIELD = {
    "text": "text",
    "url": "url",
    "video": "video",
    "picture": "picture",
    "pdf": "pdf",
    "slideshow": "slideshow",
    "screen_share": "screen_share",
}


async def _set_and_notify(screen: Any, content_type: str, content_value: str) -> dict:
    screen.type = content_type
    field = _CONTENT_VALUE_FIELD.get(content_type)
    if field is not None:
        setattr(screen, field, content_value or "")
    if content_type == "news" and content_value in {"portrait", "landscape", "presentation"}:
        screen.news_mode = content_value
    screen_manager.save_screens()
    notify_err: Optional[str] = None
    notified = False
    if screen.connected:
        try:
            await connection_manager.notify_screen(screen=screen)
            notified = True
        except Exception as e:  # noqa: BLE001
            notify_err = str(e)
    return {
        "type": screen.type,
        "value": getattr(screen, field, None) if field else None,
        "notified": notified,
        "notify_error": notify_err,
    }


async def run_content_walkthrough(
    target_screen_id: Optional[int] = None,
    state_pause_seconds: float = 4.0,
) -> dict:
    """Cycle a screen through picture → url → youtube → pdf → news →
    default settle. Returns a summary describing what was set at each
    step. Pauses `state_pause_seconds` between steps so an operator can
    see each state on the physical screen."""
    target = _pick_target(target_screen_id)
    sequence = _build_sequence()

    steps: list[dict] = []
    for label, content_type, content_value in sequence:
        if content_type == "skip":
            steps.append({"label": label, "skipped": True})
            continue
        outcome = await _set_and_notify(target, content_type, content_value)
        steps.append(
            {
                "label": label,
                "content_type": content_type,
                "content_value": content_value,
                **outcome,
            }
        )
        await asyncio.sleep(state_pause_seconds)

    return {
        "screen_id": target.id,
        "screen_name": target.name,
        "screen_connected": target.connected,
        "state_pause_seconds": state_pause_seconds,
        "steps": steps,
    }
