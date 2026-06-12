# Studio Demo Script — run from the Agent chat

Type each line into the **Studio Agent** chat panel (right side of
`http://studiopi.local:8000/admin/studio`). Wait for the agent's reply +
the studio to react before the next line. Hard-refresh the page once
before you start (Ctrl+Shift+R) so the latest UI is loaded.

Everything below runs through the real agent → MCP tools (lights, screens,
brands, VLC video, robot arm).

---

## 1 — Brand profiles (the big "wow")

> **set the brand to IKEA**

→ Blue + yellow lighting, IKEA imagery on the zone screens, IKEA video on the VLC screen.

> **now switch to Accenture**

→ Purple lighting, the Accenture logo on every screen, Accenture video.

*(Either order works. Each command sets lights + screens + video in one go.)*

---

## 2 — Editing zones live

> **change the lights in zone A to red**

→ Main Cloud's lights turn red.

> **make Station 1 warm white**

> **set Cloud L to deep blue**

*(Zones can be named — "Main Cloud", "Station 1", "Cloud L" — or lettered "zone A".
The floor plan in the UI updates to match within a few seconds.)*

---

## 3 — Saving a brand profile

After tweaking the lights/screens above:

> **save this as the Accenture profile**

→ Captures the current per-zone lights + screen content as Accenture's new default.

Prove it stuck:

> **set the brand to IKEA**
>
> **switch back to Accenture**

→ Accenture now comes back with your saved tweaks.

---

## 4 — Robot arm

> **what are you looking at?**

→ The arm's camera reports the objects it sees.

> **point at the red object**

→ The arm swings to point at it.

> **wave hello**   *(or:  react to the red object)*

> **go home**

→ The arm returns to its home pose.

**Optional finale — autonomous pick (slow!):**

> **pick up the red bottle**

→ The arm runs the calibration-free visual grasp. ⚠️ This takes **1–3 minutes**,
which is longer than one chat turn — the chat may show a timeout while the arm
keeps working, so **watch the arm, not the chat**. Needs steady, diffuse lighting
and the green/blue strips on the gripper fingers. If it can't converge it will
**safely abort** (it won't grab blindly) — just say "try again".

---

## If something looks off
- **Brand command does nothing** → hard-refresh the page; make sure you're on `/admin/studio`.
- **A screen shows old content** → say "reload all screens".
- **A screen is blank** → that display is powered off / disconnected; it'll catch up when it's back.
- **Robot says "not connected"** → the arm's controller isn't on WiFi.
