---
name: comfortable-listening
description: Play a track at normal listening volume (foreground, not background)
when_to_use: User asks to "play music", "listen to X", "regular volume", "comfortable listening", or wants music as the main thing in the room (not under another activity).
---

For foreground / focused listening:

1. `list_sounds` if the operator named a specific file; otherwise
   pick whatever fits best from `list_sounds`.
2. `play_local_file` with:
     - `file_path` = chosen file
     - `mood = "comfortable"` (HEOS level ~50)
     - `ramp_seconds` = 2 (default — still ramps from ~20 to 50,
       so the start is a gentle 2-second fade-in, not a sudden 50).
3. One-line reply: "playing <file> at comfortable level (50, 2 s
   fade-in)".

If the operator pre-emptively says "loud" or "really listen", bump
to `mood="loud"` (~65 — still under the 70 hard cap). Do NOT go
above the cap.

When playback is already active and they ask to "turn it up", call
`set_marantz_volume` — it reads the current level and ramps from
there. Down-changes are instant (always safe to drop).
