# Reinvention Studio — System Overview (for the presentation)

## The idea in one line
A room that thinks. Instead of manually configuring screens, lights, sound and
video for every client visit, an **AI agent** acts as the brain: you tell it —
by typing or by voice — *what* you want ("set the studio for IKEA", "make zone A
red", "pick up the bottle") and it orchestrates the whole space.

## The two halves

**The brain** — a Raspberry Pi (`studiopi`) running a Python/FastAPI app. It hosts:
- the **operator dashboard** (`/admin/studio`) — the visual control surface,
- a set of **MCP tool servers**, one per domain: **lighting, screens, displays,
  audio, music, video (VLC), and the robot arm**. MCP = a standard way to give an
  LLM safe, typed "tools" it can call.
- the **agent endpoint** (`/api/chat`): it runs Claude with access to those tools.
  When you type "set the brand to IKEA", Claude decides which tools to call and
  carries it out — it's the translation layer from *intent* to *action*.

**The room** — the real hardware on the studio network:
- ~8 **display screens** (each a browser showing whatever content the brain pushes),
- **Philips Hue** lights,
- **audio** (speakers + networked microphones),
- a **VLC media PC** that plays full-screen video,
- a **Braccio robot arm** with a **webcam** that lets it see and grab objects.

## The key concept: zones
The room is divided into named **zones** — Main Cloud, Station 1/2/3, Cloud L/R,
Main Hall, etc. We mapped every zone to its real screen(s) **and** its real Hue
light(s), verified physically in the room. So the system can talk about the room
the way people do ("the lights in zone A", "Station 1's screen") instead of in
hardware IDs.

## What it can do (and how)
- **Brand profiles** — one command ("set the brand to IKEA" / "…Accenture") sets
  the lights to the brand palette, puts on-brand content on every screen, and
  plays the brand video on the VLC screen. Two brands are built in (IKEA, Accenture).
- **Screens that mimic the lighting** — a screen can show an animated gradient
  whose colours follow that zone's live light colours, so screens and room light
  feel like one continuous surface.
- **Per-zone control** — "change the lights in zone A to red", "make Station 1 warm".
- **Save a look** — tweak the room live, then "save this as the IKEA profile" and
  the system remembers it as that brand's new default.
- **The robot** — "what are you looking at?", "point at the red object", "pick up
  the bottle". The arm uses its webcam to find objects and grasp them with no
  fixed calibration (it re-learns the camera↔arm relationship each time).
- **Voice or text** — the same agent, driven by typing or speech.

## Why it matters
The contrast to sell: this isn't a fixed script of buttons. The **camera is the
agent's eyes, the MCP tools are its hands, and the decisions are the model's** —
so the studio responds to plain language and curates itself for whoever walks in.

## How control flows (the one diagram to draw)
```
You (type / speak)
      │
      ▼
Studio Agent  ──/api/chat──►  Claude  ──MCP tools──►  Lighting (Hue)
(dashboard / voice)                                   Screens (content + gradients)
                                                      Video (VLC)
                                                      Audio (speakers / mics)
                                                      Robot arm (+ webcam)
```
Everything runs on the studio LAN; the Pi is the hub.
