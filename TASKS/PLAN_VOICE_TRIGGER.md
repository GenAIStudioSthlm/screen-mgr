# PLAN — Voice & Chat Trigger for Admin Test Buttons

**Status (2026-05-26):** Paused mid-session. All prerequisites done; build of the trigger pipeline itself has not started. Next session can resume directly from the build plan below.

**Update (2026-06-09):** The Sennheiser TCC has been **factory reset** — its mic-auth config is gone and we are **no longer counting on the TCC** for capture. Capture path is now locked to the **browser device mic** (`getUserMedia`/`MediaRecorder`), which was already the v1 plan. TCC capture (AES67 / Dante Virtual Soundcard) is dropped entirely, not just deferred. "Mic auth" prerequisite #1 below is now moot for v1.

---

## What we did today

### 1. Mic auth (Sennheiser TCC SSC API) — ✅ done end-to-end
- Added `SENNHEISER_TCC_USERNAME=api` + `SENNHEISER_TCC_PASSWORD=GenAiStudio88!` to `/home/admin/screen-mgr/.env` on the Pi.
- Restarted `screen-mgr.service` so the new env vars took effect.
- Verified `/api/audio/microphones/GenAi-001b664130b7/state` returns full populated `site` + `state` blocks (was 401 before).
- Verified `/api/audio/microphones/GenAi-001b664130b7/test` does the real LED-flash identification (mode = `identify`, both PUTs return 200, LED visibly flashes).
- **Gotcha logged to memory:** `[[reference-sennheiser-tcc-auth]]` — username is always `api`, not the Cockpit operator login; 3rd Party Access must be enabled in Cockpit before *any* auth-gated endpoint works, otherwise the device returns 401 regardless of password.

### 2. Whisper transcription service — ✅ running locally
- Built the container from `C:\Projects\Studio\scr-transcribe-assistant\whisper-transcriber` (was already developed by Dan).
- Image: `localhost/whisper-transcriber_whisper:latest` (13.1 GB, faster-whisper large-v3 on CUDA).
- Fixed missing GPU passthrough by installing `nvidia-container-toolkit` inside the podman WSL machine + generating the CDI spec (`nvidia-ctk cdi generate --output=/etc/cdi/nvidia.yaml`).
- Container is up on this machine: `http://192.168.2.86:8765/transcribe`, `large-v3` loaded on the RTX 5000 Ada GPU in 3.3s.
- Diarization disabled (no HF_TOKEN) — fine for 5-word commands.
- Caveat: container survives reboots (`restart: unless-stopped` in compose), but only on **this Windows machine**. If the machine is off, voice trigger is dead.

### 3. TCC AES67 attempt — ❌ rolled back, **don't retry on this network**
- Enabled RTP Mode = AES67 on the TCC via Dante Controller → PTPv2 multicast started flooding the LAN → Comhem consumer router could not cope, crashed, took the Wi-Fi with it. Big screen also went into a YouTube re-loop because WebSocket reconnect storms re-fired queued content.
- Recovered via a "Restart device" button in Sennheiser Cockpit Web (Dante Controller's reboot wasn't reachable while the network was down).
- TCC is now back to RTP Mode = None, ring green, network stable.
- Logged in memory at `[[reference-sennheiser-tcc-auth]]` under "Network constraint" — **AES67 needs managed switch with IGMP snooping + ideally a separate AV VLAN before retrying.**

### 4. Memory writes
- `reference_sennheiser_tcc_auth.md` — created; captures auth gotcha + Cockpit localhost-bind quirk + network constraint.
- `reference_pi_ssh_credentials.md` — updated; spells out that the SSH key lives in WSL only, Git Bash needs the password.

---

## Where the voice trigger build itself stands

**Started:** No.
**Blocked on:** Nothing — all prerequisites are met.

The five test endpoints we'd wire up (all already existing buttons in admin):

| Phrase             | Endpoint                                                  |
|--------------------|-----------------------------------------------------------|
| "test lights"      | `POST /api/modules/hue/run_startup_test`                  |
| "test music"       | `POST /api/music/marantz_test` (verify exact path)        |
| "test screens"     | calls `runFleetDemo()` — needs an endpoint exposed        |
| "test displays"    | `POST /api/modules/{led_panel_id}/run_test_pattern`       |
| "test mic"         | `POST /api/audio/microphones/{mic_id}/test`               |

---

## Build plan — v1 (browser mic + PTT button + typed chat)

### Inputs (two paths, same dispatch)
1. **Push-to-talk** with the laptop's mic (browser MediaRecorder). Defer TCC mic capture until the network supports AES67 OR we buy Dante Virtual Soundcard.
2. **Type in admin chat** — e.g. typing `Test lights` (with or without exclamation) fires the same dispatcher. Added per Dan's request before pause. Useful when:
   - Mic isn't available (other operator, demos, screen-share)
   - Voice transcription mis-hears
   - Fast iteration during dev

### Backend (on the Pi)
- New file: `routes/voice_routes.py`
  - `POST /api/voice/dispatch` — accepts either:
    - multipart audio blob (`file=<webm/opus>`) → forwards to Whisper → uses returned `text`
    - JSON `{text: "test lights"}` → skips Whisper, goes straight to dispatch
  - Dispatcher: regex on lowercase text matching `lights|music|screens|displays|mic` → calls the matching test endpoint internally (use `httpx.AsyncClient` to localhost).
  - Returns `{heard: "test lights", matched: "lights", endpoint: "...", result: {...}}` or `{heard: "...", matched: null}`.
- `main.py` — register the new router.
- `.env.example` + Pi `.env` — add `WHISPER_URL=http://192.168.2.86:8765`.

### Frontend (admin v2)
- New file: `static/javascript/v2/voice.js`
  - Alpine component for a floating button in the admin shell (bottom-right).
  - Hold-to-talk: `mousedown` → `MediaRecorder.start()`, `mouseup` → `MediaRecorder.stop()` + POST blob to `/api/voice/dispatch`.
  - Show transient toast with `heard` + `matched` + result OK/✗.
- New admin chat input — small text field in the same floating widget. Submit on Enter → POST JSON to same endpoint.
- Wire into `templates/admin/v2/index.html` or appropriate shell partial.

### Done = these all work
- [ ] Holding mic button + saying "test lights" → Hue runs its rainbow walk
- [ ] Typing "Test Music!" in the chat → Marantz test plays
- [ ] Holding mic button + mumbling nonsense → toast says "didn't match"
- [ ] Whisper container off → typed chat still works (graceful degradation)

### Estimate
- Backend route + dispatcher: ~1 hour
- Frontend PTT + chat widget: ~2-3 hours
- Wiring + testing + iterating on the regex: ~1 hour
- **Half-day total.**

---

## Open decisions for next session

1. **Permanent home for Whisper.** This Windows laptop is convenient now but if Dan closes the lid, voice dies. Options: (a) accept it for v1, (b) move to a dedicated GPU machine, (c) run a small Whisper model on the Pi CPU (slow but always-on fallback).
2. **TCC audio capture.** Out of scope for v1 (PTPv2 incident proved AES67 isn't viable on the Comhem network). When we're ready to revisit: buy Dante Virtual Soundcard ($30, on the GPU machine) — clean path that doesn't touch PTPv2.
3. **Wake word vs PTT.** v1 is PTT to avoid the echo-loop problem (room speakers play test tones during "Test Music"). Wake-word + always-listening is a separate project.
4. **Language detection.** Whisper auto-detects; English-only forcing might reduce confusion if Swedish creeps in. Defer to v2 unless it bites.

---

## How to resume

1. Verify Whisper container is up (see runbook below). If down, start it.
2. Verify Pi is reachable: `ping 192.168.2.65` (or `ssh admin@studiopi` with password `admin`).
3. Verify mic auth is still working: `curl -sS http://studiopi:8000/api/audio/microphones/GenAi-001b664130b7/state` — should show `auth_configured: true` plus a populated `state` block.
4. Start with the backend route — `routes/voice_routes.py` is the smallest possible piece and can be tested with `curl -F` before any frontend exists.

---

## Whisper container runbook

The container is **stopped at end of session 2026-05-26** to save GPU/VRAM and laptop power. Image and build artifacts persist; only the running container is gone.

### Start
```bash
cd C:/Projects/Studio/scr-transcribe-assistant/whisper-transcriber
podman-compose up -d
```
First start after a host reboot takes ~10-15s to load `large-v3` onto the GPU. Verify ready:
```bash
podman logs --tail 5 whisper-transcriber   # look for "Whisper loaded in N.Ns"
curl -sS http://127.0.0.1:8765/docs -o /dev/null -w 'HTTP %{http_code}\n'   # expect 200
```

### Stop
```bash
cd C:/Projects/Studio/scr-transcribe-assistant/whisper-transcriber
podman-compose down
```

### Status
```bash
podman ps --filter name=whisper         # is it running?
podman logs --tail 30 whisper-transcriber   # recent activity
```

### Where it listens
- **Container** → `http://0.0.0.0:8000` (inside the WSL podman machine)
- **Host port mapping** → `http://192.168.2.86:8765` (LAN), `http://127.0.0.1:8765` (local)
- Pi at `192.168.2.65` can reach the LAN address (same subnet) — that's how the voice dispatch route will call it.

### Prerequisites (already done, only redo if podman machine is rebuilt)
- `podman machine` running on WSL2 (Fedora 42 inside)
- `nvidia-container-toolkit` installed inside the podman machine
- CDI spec at `/etc/cdi/nvidia.yaml` (regenerate with `sudo nvidia-ctk cdi generate --output=/etc/cdi/nvidia.yaml` from inside `podman machine ssh`)
- `nvidia.com/gpu=all` device reference in `podman-compose.yml` (already set)

### Failure modes seen and how to handle
- **"unresolvable CDI devices nvidia.com/gpu=all"** → CDI spec missing, regenerate it (see above).
- **OOM on first model load** → bump podman machine memory: `podman machine set --memory 8192 && podman machine stop && podman machine start`.
- **`/transcribe` returns 500** → check `podman logs whisper-transcriber` for stack trace.
