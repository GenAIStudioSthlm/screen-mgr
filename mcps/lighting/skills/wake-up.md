---
name: wake-up
description: Bring the studio up to a bright, alert workday lighting level
when_to_use: User asks for "wake up", "lights on", "morning mode", "full brightness", or any bright-workday lighting request
---

To wake the studio:

1. Check `list_scenes` for a scene named "Daylight", "Bright", "Energise", or similar. If one exists, recall it via `recall_scene` — that's the user's preferred bright preset.
2. Otherwise, fall back to per-room writes:
   - Call `list_groups` to get both rooms (typically "Maker" and "Studio").
   - For each room: `set_group(group_id, on=True, brightness_pct=100, kelvin=4500)` — cool, full-brightness work lighting.
3. Confirm what changed: "Maker + Studio rooms up to 100%, cool white." Or "Recalled scene 'Daylight'."

Don't touch rooms or scenes the user didn't ask about. If only one room is named in the request, only act on that room.
