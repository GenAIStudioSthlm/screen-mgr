"""Fleet-wide content demo — drives every available screen through 3
content modes in unison, then lands on the AI News scene.

Sequence (~17s at 4s/step):

  1. URL web      — all targets → https://example.com
  2. URL YouTube  — all targets → a YouTube embed
  3. Default      — all targets → the studio logo
  Settle          → `scene_manager.apply("ai-news")`

Target selection priority:
  1. Explicit `target_screen_ids` if passed.
  2. Otherwise: every screen with a live WebSocket (`connected=True`).
  3. If none are connected: every configured screen — keeps the data
     layer exercised even when no station is online. We surface which
     branch was taken in the response (`target_source`).

Shared between the MCP tool (`run_fleet_demo` in server.py) and the CLI
script (`scripts/screens_fleet_demo.py`).
"""

from __future__ import annotations

import asyncio
from typing import Any, Optional

from connections import connection_manager
from models.scenes import scene_manager
from screens import screen_manager


GENERIC_URL = "https://example.com"
YOUTUBE_EMBED_URL = "https://www.youtube.com/embed/aqz-KE-bpKQ"

# (label, content_type, content_value) — the 3-mode cycle.
DEFAULT_MODES: list[tuple[str, str, str]] = [
    ("url (web)", "url", GENERIC_URL),
    ("url (YouTube)", "url", YOUTUBE_EMBED_URL),
    ("default (studio logo)", "default", ""),
]

# Type-specific value field on the Screen model. Matches the mapping in
# routes/api_routes.py::set_screen_content and mcps/screens/walkthrough.py
# — see commit history if you change it; both call sites need updating.
_CONTENT_VALUE_FIELD = {
    "text": "text",
    "url": "url",
    "video": "video",
    "picture": "picture",
    "pdf": "pdf",
    "slideshow": "slideshow",
    "screen_share": "screen_share",
}


def _resolve_targets(target_screen_ids: Optional[list[int]]):
    """Return (list_of_screen_objects, source_label).

    source_label is one of: "explicit", "connected", "fallback_all".
    """
    if target_screen_ids:
        targets = [
            s for s in screen_manager.screens if s.id in set(target_screen_ids)
        ]
        return targets, "explicit"

    connected = [s for s in screen_manager.screens if s.connected]
    if connected:
        return connected, "connected"

    return list(screen_manager.screens), "fallback_all"


async def _apply_mode_to_targets(
    targets: list[Any], content_type: str, content_value: str
) -> dict:
    """Set the content on every target screen, save once, notify each.
    Returns per-screen outcomes."""
    notified: list[int] = []
    skipped: list[dict] = []

    for screen in targets:
        screen.type = content_type
        field = _CONTENT_VALUE_FIELD.get(content_type)
        if field is not None:
            setattr(screen, field, content_value or "")
        # "default" needs no value; news_mode handled by other tools.

    # Single save for the batch — small file write, no need to flush
    # per-screen.
    screen_manager.save_screens()

    for screen in targets:
        if not screen.connected:
            skipped.append({"id": screen.id, "reason": "not connected"})
            continue
        try:
            await connection_manager.notify_screen(screen=screen)
            notified.append(screen.id)
        except Exception as e:  # noqa: BLE001
            skipped.append({"id": screen.id, "reason": str(e)})

    return {"notified": notified, "skipped": skipped}


async def run_fleet_demo(
    target_screen_ids: Optional[list[int]] = None,
    state_pause_seconds: float = 4.0,
    settle_scene_id: str = "ai-news",
    modes: Optional[list[tuple[str, str, str]]] = None,
) -> dict:
    """Cycle every target screen through 3 modes, then settle on a scene.

    Returns a per-step summary.

    - ``target_screen_ids``: optional explicit list. Otherwise picks
      connected screens, with a fallback to every configured screen.
    - ``state_pause_seconds``: pause between modes (default 4.0).
    - ``settle_scene_id``: scene applied at the end. Default
      ``ai-news`` matches the seeded scene.
    - ``modes``: override the 3-mode cycle. Tuple format is
      ``(label, content_type, content_value)``.
    """
    targets, source = _resolve_targets(target_screen_ids)
    sequence = modes or DEFAULT_MODES

    steps: list[dict] = []
    for label, content_type, content_value in sequence:
        outcome = await _apply_mode_to_targets(targets, content_type, content_value)
        steps.append(
            {
                "label": label,
                "content_type": content_type,
                "content_value": content_value,
                **outcome,
            }
        )
        await asyncio.sleep(state_pause_seconds)

    # Settle on the named scene — uses the same logic the HTTP route
    # /api/scenes/{id}/apply uses (SceneManager.apply), so this exercises
    # both the per-screen write path and the scene-apply path in one test.
    try:
        settle_result: dict = await scene_manager.apply(settle_scene_id)
    except KeyError:
        settle_result = {"error": f"scene_id {settle_scene_id!r} not found"}

    return {
        "targets": [s.id for s in targets],
        "target_source": source,
        "settle_scene_id": settle_scene_id,
        "state_pause_seconds": state_pause_seconds,
        "steps": steps,
        "settle_result": settle_result,
    }
