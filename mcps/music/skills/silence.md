---
name: silence
description: Stop or pause music on the Marantz
when_to_use: User asks for "silence", "stop the music", "pause", "kill the audio", "shut it off", or any variant.
---

To silence music:

- "stop" / "shut it off" / "kill it" → `marantz_stop` (state=stop;
  the URL stream source goes idle; AVR returns to its previous
  display)
- "pause" / "hold it" → `marantz_pause` (state=pause; can resume
  with `marantz_resume`)
- "mute" → semantically the same as stop in our setup; we don't have
  a separate mute that preserves the source. Use `marantz_stop`.

Reply in one short line confirming the action — operators need
fast feedback when they ask for silence.

Do NOT lower the volume to 0 as a "silence" — that leaves the source
selected on the AVR. Always actually stop/pause.
