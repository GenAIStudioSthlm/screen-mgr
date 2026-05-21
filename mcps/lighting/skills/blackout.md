---
name: blackout
description: Turn off every light in the studio for a hard stop or end-of-day
when_to_use: User asks for "blackout", "all off", "lights off", "kill the lights", "shut it down", or similar full-off request
---

To black out everything:

1. Call `all_off` — turns off every light known to the bridge in one round-trip.
2. Confirm: "All lights off."

To black out a single room (e.g. "blackout the Studio"):

1. Use `list_groups` to find the named room and its `group_id`.
2. Call `set_group(group_id, on=False)`.
3. Confirm with the room name: "Studio lights off." (Maker stays as-is.)

Do not use `all_off` for a single-room request — that would also kill the other room's lights.
