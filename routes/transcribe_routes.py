"""POST /api/transcribe — proxy browser audio to the Whisper service.

The admin chat's push-to-talk records a short clip in the browser
(`MediaRecorder`, webm/opus) and POSTs it here. We forward it to the
local faster-whisper service on the GPU box and return the transcript as
plain JSON ``{"text": "..."}``.

Why proxy instead of letting the browser hit Whisper directly:
  - Whisper sends no CORS headers, so a cross-origin browser POST is blocked.
  - Keeps the GPU box address server-side (one env var, `WHISPER_URL`).
  - Survives a future move to HTTPS for the admin (no mixed-content block).

If the Whisper box is off/unreachable we return 502 with a clear message;
the frontend surfaces it and typed chat keeps working.
"""

from __future__ import annotations

import os

import httpx  # bundled via the anthropic SDK dependency
from fastapi import APIRouter, File, UploadFile
from fastapi.responses import JSONResponse


router = APIRouter()

# GPU box running the faster-whisper container (see its runbook). Override
# per-deploy in .env; default matches the studio LAN address.
_WHISPER_URL = os.environ.get("WHISPER_URL", "http://192.168.2.86:8765").rstrip("/")

# Studio vocabulary primes Whisper so domain words land correctly and it
# doesn't drift to Swedish on a 2-word command. English-forced — flip to
# auto-detect (drop `language`) if multilingual commands are ever needed.
_INITIAL_PROMPT = (
    "Studio control commands: lights, Hue, brightness, scene, presentation, "
    "blackout, screens, displays, LED panels, microphone, Marantz, music, "
    "Spotify, play, test."
)

# Whisper on a warm GPU handles a few-second clip in well under this; the
# ceiling just stops a hung request from wedging the chat mic.
_TIMEOUT_S = 30.0


@router.get("/api/transcribe/health")
async def transcribe_health():
    """Is the Whisper service reachable and its model loaded? The chat UI
    probes this on load to decide between Whisper and the cloud Web Speech
    fallback."""
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            resp = await client.get(f"{_WHISPER_URL}/health")
        body = resp.json()
        return {"available": resp.status_code == 200 and body.get("status") == "ok"}
    except Exception:
        return {"available": False}


@router.post("/api/transcribe")
async def transcribe(file: UploadFile = File(...)):
    """Forward an audio clip to Whisper and return its transcript text."""
    audio = await file.read()
    if not audio:
        return JSONResponse({"error": "empty audio"}, status_code=400)

    files = {
        "file": (
            file.filename or "audio.webm",
            audio,
            file.content_type or "audio/webm",
        )
    }
    data = {
        "language": "en",
        "task": "transcribe",
        "output_format": "json",
        "initial_prompt": _INITIAL_PROMPT,
    }

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_S) as client:
            resp = await client.post(
                f"{_WHISPER_URL}/transcribe", files=files, data=data
            )
    except httpx.RequestError as e:
        return JSONResponse(
            {
                "error": (
                    "Whisper service unreachable at "
                    f"{_WHISPER_URL} — is the GPU box on and the container "
                    f"running? ({e.__class__.__name__})"
                )
            },
            status_code=502,
        )

    if resp.status_code != 200:
        return JSONResponse(
            {"error": f"whisper returned {resp.status_code}: {resp.text[:200]}"},
            status_code=502,
        )

    payload = resp.json()
    return {"text": (payload.get("text") or "").strip()}
