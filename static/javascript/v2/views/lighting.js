/* views/lighting.js — Alpine.data factory for the v2 Lighting view.
 *
 * Pulls live Hue state from /api/modules/hue/* and renders:
 *   - bridge status (paired / available)
 *   - per-zone scoped controls when the shell has a zone selected
 *     (reads `selected` inherited from the shell's outer scope)
 *   - global rooms (all groups) and scene buttons
 *   - individual light list (collapsible)
 *
 * Polls every 8s.
 */
document.addEventListener('alpine:init', () => {
  Alpine.data('v2LightingView', () => ({
    hue: { paired: false, available: false, bridge_ip: '' },
    lights: {},
    groups: {},
    scenes: {},
    showLights: false,
    lastAction: '',
    lastActionOk: true,
    _timer: null,

    async load() {
      try {
        const r = await fetch('/api/modules/hue');
        const m = await r.json();
        this.hue = m.status || { paired: false, available: false };
      } catch (e) {
        this.hue = { paired: false, available: false };
      }
      if (this.hue.available) {
        try {
          const [lr, gr, sr] = await Promise.all([
            fetch('/api/modules/hue/lights').then(r => r.json()),
            fetch('/api/modules/hue/groups').then(r => r.json()),
            fetch('/api/modules/hue/scenes').then(r => r.json()),
          ]);
          this.lights = lr || {};
          this.groups = gr || {};
          const named = {};
          for (const [id, s] of Object.entries(sr || {})) {
            if (s && s.name) named[id] = s;
          }
          this.scenes = named;
        } catch (e) { console.error('lighting load failed', e); }
      }
      clearTimeout(this._timer);
      this._timer = setTimeout(() => this.load(), 8000);
    },

    async _put(url, body) {
      try {
        const r = await fetch(url, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });
        await r.json();
        this.lastAction = url + ' ✓';
        this.lastActionOk = true;
      } catch (e) {
        this.lastAction = url + ' ✗ ' + e;
        this.lastActionOk = false;
      }
    },
    async _post(url) {
      try {
        await fetch(url, { method: 'POST' });
        this.lastAction = url + ' ✓';
        this.lastActionOk = true;
      } catch (e) {
        this.lastAction = url + ' ✗ ' + e;
        this.lastActionOk = false;
      }
    },

    async toggleZone(zone) {
      if (!zone?.light_group_id) return;
      const g = this.groups[zone.light_group_id] || {};
      const any = !!(g.state?.any_on || g.action?.on);
      await this._put('/api/modules/hue/groups/' + zone.light_group_id, { on: !any });
      await this.load();
    },
    async setZoneBri(zone, value) {
      if (!zone?.light_group_id) return;
      await this._put('/api/modules/hue/groups/' + zone.light_group_id, { on: true, bri: parseInt(value) });
    },
    zoneGroup(zone) {
      if (!zone?.light_group_id) return null;
      return this.groups[zone.light_group_id] || null;
    },

    async toggleGroup(id, g) {
      const any = !!(g.state?.any_on || g.action?.on);
      await this._put('/api/modules/hue/groups/' + id, { on: !any });
      await this.load();
    },
    async setGroupBri(id, value) {
      await this._put('/api/modules/hue/groups/' + id, { on: true, bri: parseInt(value) });
    },

    async toggleLight(id, l) {
      const want = !(l.state && l.state.on);
      await this._put('/api/modules/hue/lights/' + id, { on: want });
      await this.load();
    },
    async setLightBri(id, value) {
      await this._put('/api/modules/hue/lights/' + id, { on: true, bri: parseInt(value) });
    },
    async setLightColor(id, hex) {
      const xy = hexToXy(hex);
      await this._put('/api/modules/hue/lights/' + id, { on: true, xy: xy });
    },

    async recallScene(id) {
      await this._post('/api/modules/hue/scenes/' + id + '/recall');
    },
    async allOn()  { await this._post('/api/modules/hue/all/on');  await this.load(); },
    async allOff() { await this._post('/api/modules/hue/all/off'); await this.load(); },

    hueToHexLight(l) {
      const s = (l && l.state) || {};
      if (s.hue == null || s.sat == null) return '#ffffff';
      return hsvToHex(s.hue / 65535, s.sat / 254, (s.bri ?? 254) / 254);
    },
    rooms() {
      return Object.entries(this.groups).filter(([id, g]) => (g && g.type) === 'Room');
    },
  }));
});

// ---- color helpers (shared between views; kept inline here for v1) ----
function hexToXy(hex) {
  let r = parseInt(hex.substr(1, 2), 16) / 255;
  let g = parseInt(hex.substr(3, 2), 16) / 255;
  let b = parseInt(hex.substr(5, 2), 16) / 255;
  r = (r > 0.04045) ? Math.pow((r + 0.055) / 1.055, 2.4) : r / 12.92;
  g = (g > 0.04045) ? Math.pow((g + 0.055) / 1.055, 2.4) : g / 12.92;
  b = (b > 0.04045) ? Math.pow((b + 0.055) / 1.055, 2.4) : b / 12.92;
  const X = r * 0.664511 + g * 0.154324 + b * 0.162028;
  const Y = r * 0.283881 + g * 0.668433 + b * 0.047685;
  const Z = r * 0.000088 + g * 0.072310 + b * 0.986039;
  const d = X + Y + Z;
  if (d === 0) return [0.32, 0.34];
  return [X / d, Y / d];
}
function hsvToHex(h, s, v) {
  const i = Math.floor(h * 6);
  const f = h * 6 - i;
  const p = v * (1 - s);
  const q = v * (1 - f * s);
  const t = v * (1 - (1 - f) * s);
  let r, g, b;
  switch (i % 6) {
    case 0: r = v; g = t; b = p; break;
    case 1: r = q; g = v; b = p; break;
    case 2: r = p; g = v; b = t; break;
    case 3: r = p; g = q; b = v; break;
    case 4: r = t; g = p; b = v; break;
    default: r = v; g = p; b = q;
  }
  const hex = n => Math.round(n * 255).toString(16).padStart(2, '0');
  return '#' + hex(r) + hex(g) + hex(b);
}
