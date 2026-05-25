# Safety — acoustic feedback prevention

The studio has an always-on ceiling microphone (Sennheiser TC Ceiling
Medium) and a high-output amp + speaker chain (Marantz Cinema 70s plus
the room's speakers). Any closed loop between them can build acoustic
feedback within seconds and **damage the speakers, the amp, or both**.
This doc captures the design rules every audio-output code path must
honour, the rails we've already built, and the rails still owed.

> Read this before touching `mcps/audio/*`, `mcps/music/*`,
> `routes/audio_routes.py`, `routes/music_routes.py`, or any future
> room-voice / TTS / agent-response code.

## The loop we're avoiding

```
        ┌──────────────────────────────────────────────────┐
        │                                                  │
        │  Speakers (Marantz 70s + studio)                 │
        │     ▲                                  │         │
        │     │ amplified output                 │ acoustic│
        │     │                                  │ coupling│
        │  ┌──┴──────────┐                       ▼         │
        │  │ Audio MCP   │                  ┌──────────┐   │
        │  │ play_sound  │                  │ TCC mic  │   │
        │  │ Spotify     │                  └────┬─────┘   │
        │  │ TTS reply   │                       │         │
        │  └─────────────┘                       │         │
        │     ▲                                  ▼         │
        │     │                            ┌──────────┐    │
        │     └─── orchestrator reply ◄────┤  STT /   │    │
        │                                  │ /api/chat│    │
        │                                  └──────────┘    │
        └──────────────────────────────────────────────────┘
```

If the mic captures the speaker output (it will — it's a ceiling
omnidirectional array directly above the listening position), and that
audio is transcribed and responded-to via the speakers, gain stacks each
round trip. Without intervention it's seconds to clipping, **tens of
seconds to driver damage** at the Marantz's output levels.

## Volume calibration (the Marantz + Bose chain)

Volume numbers in the codebase are on the **HEOS 0-100 scale**, which
maps onto the AVR's master volume in dB. **This is not perceived
loudness percent.** "50" is not "half as loud as max"; it is the dB
level that sounded right for normal listening on this specific
receiver during calibration on 2026-05-25.

| HEOS level | Approx master dB | Feels like |
|---|---|---|
| 10 | ~-60 dB | inaudible — silent for practical purposes |
| 25 | ~-45 dB | whisper / very low — confirms playback works |
| 35 | ~-30 dB | background — easy to talk over |
| 50 | ~-25 dB | comfortable / regular listening |
| 65 | ~-15 dB | loud — focus-the-room level, near max |
| 70 | ~-15 dB | **HARD CAP** — refused above this |

The agent's semantic vocabulary maps named moods to safe defaults:

| Mood | Level | Use |
|---|---|---|
| `inaudible` | 10 | Confirms a code path works without making sound |
| `whisper` | 25 | First-test default (`SAFE_TEST_VOLUME_PCT`) |
| `background` | 35 | "Play me some background music" |
| `comfortable` | 50 | "Normal listening" |
| `loud` | 65 | "Crank it up" — still under the cap |
| `max` | 70 | The cap. Anything higher is refused. |

Agents should prefer `mood="..."` over `volume_pct=N` when the user's
intent is vague ("play me a background track"). The Music MCP's
`get_volume_calibration` tool returns this whole table as data so
agents can read it programmatically.

## Rule 1 — hard volume ceiling on every write path

Every code path that ends in "speakers play sound" must clamp the
requested level through a single shared safety gate:

```python
from mcps.audio.safety import cap_volume
effective_pct, was_capped = cap_volume(requested_pct)
```

`cap_volume` reads `MAX_OUTPUT_VOLUME_PCT` from `.env`
(**default 70**), clamps `[0, ceiling]`, and tells the caller if it
clipped. Callers should surface `was_capped` in their result dict so
the operator / agent knows the asked-for value didn't fully land.

**Currently enforced in:**
- `mcps/audio/pactl_backend.set_volume` (PulseAudio sinks)
- `mcps/music/server.set_volume` (Spotify volume MCP tool)
- `mcps/music/speaker_test.run_speaker_test` (volume_pct param)
- `mcps/music/presets.play_preset` (preset default + override)

**Not yet relevant (no code path exists) but must apply when built:**
- `play_sound` already routes through `pactl set-sink-volume`, so the
  sink's level is capped — but the file's own loudness still matters;
  see Rule 4.
- Any future TTS / synthesised reply on the speakers.
- Any future "preview track" or "duck music for announcement" feature.

**Raising the cap**: set `MAX_OUTPUT_VOLUME_PCT=N` in
`/home/admin/screen-mgr/.env`. Don't do this without thinking through
the feedback model for the *specific* mic + speaker geometry currently
in the room. 70 is conservative on purpose.

## Rule 2 — mute the mic while we're playing

Not yet implemented. When a code path knows audio is about to play out
the room speakers, it should:

1. Mute the TCC via `PUT /api/device/identification` …no wait — the
   actual mute path is the SSCv2 audio tree which we can't reach until
   `SENNHEISER_TCC_PASSWORD` is set (see PLAN_AGENTIC Phase 11).
2. Start playback.
3. Wait for the file / track / TTS reply to finish.
4. Unmute the mic.

Until the SSCv2 password lands, **the room voice → chat → speaker loop
must stay disconnected**. The chat UI today uses the BROWSER's mic
(Web Speech API) — the operator's laptop, not the ceiling mic — so
there's no loop today. Don't wire the TCC into `/api/chat` until Rule 2
is enforceable.

## Rule 3 — push-to-talk only for room voice (no continuous listening)

The Phase 8 room-voice daemon (`scripts/room_voice.py`, future) must
require an explicit trigger to capture audio: GPIO button press, a wake
word with strict gating, or an operator click in the admin UI. **No
continuous listening that auto-fires `/api/chat`** — that's the path
that closes the loop most easily.

Push-to-talk is also Rule 1's friend: when the human is talking, the
speakers should be ducked anyway.

## Rule 4 — half-duplex by default

When the agent is mid-response (TTS or music starting), the mic input
should be ignored even if currently capturing. The simplest
implementation: a single `playback_in_progress` flag the
voice daemon checks before forwarding a transcript. If set, drop the
transcript.

This catches the case where Rule 2's mute hasn't propagated yet (TCC
mute takes ~100 ms over the network), or the operator unmutes mid-reply.

## Rule 5 — loud-input → emergency mute (future, optional)

If we ever observe the mic's input level spiking unusually fast
(`d/dt(level) > threshold`), auto-mute the speakers + the mic and log
a feedback-detection event. This is DSP work and most realistically
lives on the TCC itself (its SSC2 surface exposes per-channel levels)
or in a `gst-launch` audio-monitor side-car. Out of scope for the
current code base; document the threshold + the action when we build it.

## What's safe today (without these rails)

- The admin UI sliders + the Spotify embedded player target the
  Marantz at moderate volumes; the user pre-sets the AVR's own level.
- The Audio MCP `play_sound` only plays files under `static/sounds/`
  (path-restricted) — currently empty, so nothing actually plays.
- The chat panel uses the BROWSER mic, not the TCC.
- The Marantz has its own input gain you can pre-set conservatively.

## What is NOT safe yet — do not wire without rails

- **TCC mic into `/api/chat` over the room speakers.** Needs Rules 2 +
  3 + 4 enforceable, which need the SSCv2 password to mute the mic
  programmatically.
- **Any agent-driven TTS reply on the room speakers.** Needs Rules 1
  (already there) + Rule 4.
- **Auto-playing music in response to room speech.** Same — needs at
  least Rule 4.

## Environment variables

| Var | Default | What |
|---|---|---|
| `MAX_OUTPUT_VOLUME_PCT` | `70` | Hard ceiling clamped onto every volume-write code path. |
| `SENNHEISER_TCC_PASSWORD` | _(unset)_ | Unlocks mic mute control — required to enforce Rule 2. |
| `SENNHEISER_TCC_USERNAME` | `api` | HTTP Basic username for the TCC's SSCv2 API. |

## See also

- [`mcps/audio/safety.py`](../mcps/audio/safety.py) — the actual `cap_volume` implementation
- [`TASKS/PLAN_AGENTIC.md`](../TASKS/PLAN_AGENTIC.md) — Phase 11 (room voice + AES67 + SSCv2)
- [`docs/EXTERNAL_INTEGRATION.md`](EXTERNAL_INTEGRATION.md) — how external services drive audio, and what limits they must respect
