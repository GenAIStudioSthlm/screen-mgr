---
name: presentation-mode
description: Dim the Studio room lights to a warm, focused presentation level
when_to_use: User asks for "presentation mode", "demo lights", "dim for a meeting", "set up for presenting", or similar
---

To set up presentation mode:

1. Call `list_groups` to find the room. The Studio room is the group whose `name == "Studio"`.
2. Check `list_scenes` for an existing scene whose name suggests presentation (e.g. "Presentation", "Dimmed", "Focus"). If one exists, recall it via `recall_scene` and stop — the user's pre-tuned scene almost always beats a generic dim.
3. Otherwise, fall back to: `set_group(group_id=<Studio>, on=True, brightness_pct=30, kelvin=2700)` — warm white, focused level.
4. Do NOT touch the Maker room or any other zone — presentation mode is Studio-only unless the user said otherwise.
5. Confirm in one sentence: "Studio dimmed to presentation mode."
