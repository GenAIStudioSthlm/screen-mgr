---
name: background-music
description: Pick a local track and play it as background music under conversation / video / work
when_to_use: User asks for "background music", "play something underneath", "ambient", "set the mood", "studio background", or describes a vibe to play quietly.
---

To play background music:

1. Call `list_sounds` to see what local files are available.
2. If the operator named a vibe (chill, lo-fi, ambient, beats, etc.),
   pick the closest file by name. If they didn't name anything,
   pick the most recently-added file or the one that sounds
   ambient-friendly.
3. Call `play_local_file` with:
     - `file_path` = the chosen file
     - `mood = "background"` (HEOS level ~35 — easy to talk over)
     - keep `ramp_seconds` at the default (2 s) so it fades in
4. Reply in one short line: "playing <file> as background (level ~35,
   2 s fade-in)".

Don't pass `ramp_seconds=0` for background — the whole point is a
gentle fade-in.

If the operator says "louder" while it's playing, use
`set_marantz_volume(mood="comfortable")` — UP changes ramp gracefully.
"Quieter" or "stop" goes through `set_marantz_volume(mood="whisper")`
or `marantz_stop` respectively.
