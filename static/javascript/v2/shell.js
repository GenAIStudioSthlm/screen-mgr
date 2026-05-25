/* shell.js — Alpine x-data factory for the /admin layout.
 *
 * Registered as Alpine data on the `alpine:init` event, which fires
 * before Alpine processes any x-data attribute. This avoids the
 * timing/scope quirks of relying on `window.studioShell` being set
 * before Alpine evaluates `<body x-data="studioShell()">`.
 */
function studioShell() {
  return {
    zones: [],
    selected: null,
    view: 'screens',
    clock: '',
    _zoneTimer: null,

    // Device positions on the floor plan
    positions: {},          // {kind: {id: {x, y}}}
    placeables: [],         // [{kind, id, name, placed, online}]
    editPositions: false,
    placing: null,          // {kind, id, name} or null while in click-to-place mode
    positionMsg: '',
    positionMsgOk: true,
    _dragging: null,        // {kind, id, svgEl} during a drag

    async load() {
      this.startClock();
      await Promise.all([
        this.refreshZones(),
        this.refreshScenes(),
        this.refreshPositions(),
      ]);
    },

    async refreshZones() {
      try {
        const r = await fetch('/api/zones');
        const d = await r.json();
        this.zones = d.zones || [];
        if (this.selected) {
          this.selected = this.zones.find(z => z.id === this.selected.id) || null;
        }
      } catch (e) {
        console.error('zones load failed', e);
      }
      clearTimeout(this._zoneTimer);
      this._zoneTimer = setTimeout(() => this.refreshZones(), 8000);
    },

    select(z) {
      this.selected = z;
    },

    // Scenes
    scenes: [],
    sceneActionMsg: '',
    sceneActionOk: true,
    sceneDropdownOpen: false,

    async refreshScenes() {
      try {
        const r = await fetch('/api/scenes');
        const d = await r.json();
        this.scenes = d.scenes || [];
      } catch (e) { console.error('scenes load failed', e); }
    },

    async applyScene(sceneId) {
      this.sceneActionMsg = 'applying…';
      this.sceneActionOk = true;
      this.sceneDropdownOpen = false;
      try {
        const r = await fetch('/api/scenes/' + sceneId + '/apply', { method: 'POST' });
        const d = await r.json();
        const updated = (d.screens_updated || []).length;
        const reloaded = (d.reloaded || []).length;
        const failed = (d.screens_failed || []).length;
        const hueNote = d.hue && d.hue.error ? ' · hue: ' + d.hue.error : (d.hue ? ' · hue ✓' : '');
        this.sceneActionMsg = sceneId + ' ✓ — ' + updated + ' screens updated · ' + reloaded + ' reloaded' + (failed ? ' · ' + failed + ' failed' : '') + hueNote;
        this.sceneActionOk = failed === 0;
        await this.refreshZones();
      } catch (e) {
        this.sceneActionMsg = sceneId + ' ✗ ' + e;
        this.sceneActionOk = false;
      }
    },

    startClock() {
      const t = () => {
        const d = new Date();
        this.clock = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      };
      t();
      setInterval(t, 1000);
    },

    // ----------------------------------------------------------------
    // Floor-plan positions: read state, build the placeable device
    // list, click-to-place, drag-to-reposition.
    // ----------------------------------------------------------------

    async refreshPositions() {
      try {
        const r = await fetch('/api/positions');
        const d = await r.json();
        this.positions = d.positions || {};
      } catch (e) {
        console.error('positions load failed', e);
        this.positions = {};
      }
      await this.refreshPlaceables();
    },

    async refreshPlaceables() {
      // Fetch each device-listing endpoint in parallel; tolerate
      // individual failures (the affected kind just shows nothing).
      let screens = [];
      let lights = {};
      let mics = [];
      try {
        const results = await Promise.allSettled([
          fetch('/api/screens').then(r => r.json()),
          fetch('/api/modules/hue/lights').then(r => r.json()),
          fetch('/api/audio/microphones').then(r => r.json()),
        ]);
        if (results[0].status === 'fulfilled') screens = results[0].value.screens || [];
        if (results[1].status === 'fulfilled') lights = results[1].value || {};
        if (results[2].status === 'fulfilled') mics = results[2].value.microphones || [];
      } catch (e) { /* swallowed individually above */ }

      const placedIn = (kind, id) =>
        !!(this.positions[kind] && this.positions[kind][String(id)]);

      const list = [];

      // Stations (screens). The "main screen" is one of the eight.
      for (const sc of screens) {
        list.push({
          kind: 'station',
          id: String(sc.id),
          name: sc.name || ('Station ' + sc.id),
          placed: placedIn('station', sc.id),
          online: !!sc.connected,
        });
      }

      // Hue lights
      for (const [lightId, l] of Object.entries(lights)) {
        if (!l || typeof l !== 'object') continue;
        list.push({
          kind: 'light',
          id: String(lightId),
          name: l.name || ('Light ' + lightId),
          placed: placedIn('light', lightId),
          online: l.state && l.state.reachable !== false,
        });
      }

      // Hardcoded singletons — display + speaker. Extend if more land.
      list.push({
        kind: 'display', id: 'rgbdisplay', name: 'RGB LED Matrix',
        placed: placedIn('display', 'rgbdisplay'), online: true,
      });
      list.push({
        kind: 'speaker', id: 'marantz', name: 'Marantz CINEMA 70s',
        placed: placedIn('speaker', 'marantz'), online: true,
      });

      // Networked microphones (Sennheiser TCC family)
      for (const m of mics) {
        if (!m || m.error || m._error) continue;
        list.push({
          kind: 'microphone',
          id: m.id,
          name: m.friendly_name || m.hostname || m.id,
          placed: placedIn('microphone', m.id),
          online: true,
        });
      }

      this.placeables = list;
    },

    /* user toggled the edit mode chip; clear placing state when
       leaving edit mode so the next entry is a clean slate. */
    toggleEditPositions() {
      this.editPositions = !this.editPositions;
      if (!this.editPositions) {
        this.placing = null;
        this.positionMsg = '';
      }
    },

    /* clicked a device in the tray — enter "placing" mode for it. */
    startPlacing(device) {
      if (!this.editPositions) return;
      if (this.placing && this.placing.kind === device.kind && this.placing.id === device.id) {
        this.placing = null;
        this.positionMsg = '';
        return;
      }
      this.placing = { kind: device.kind, id: device.id, name: device.name };
      this.positionMsg = 'Click on the floor plan to place: ' + device.name;
      this.positionMsgOk = true;
    },

    /* convert clientX/Y → SVG viewBox coords for a placement event. */
    _svgPoint(event, svgEl) {
      if (!svgEl || !svgEl.createSVGPoint) return null;
      const pt = svgEl.createSVGPoint();
      pt.x = event.clientX;
      pt.y = event.clientY;
      const ctm = svgEl.getScreenCTM();
      if (!ctm) return null;
      return pt.matrixTransform(ctm.inverse());
    },

    async onPlanClick(event) {
      // Only act when we're explicitly placing a device. Other clicks
      // (e.g. zone selection) still bubble through the polygon handlers.
      if (!this.placing) return;
      const svgEl = event.currentTarget.closest('svg');
      if (!svgEl) return;
      const p = this._svgPoint(event, svgEl);
      if (!p) return;
      const placed = this.placing;
      await this._putPosition(placed.kind, placed.id, p.x, p.y);
      this.positionMsg = 'Placed ' + placed.name + ' at (' +
                          Math.round(p.x) + ', ' + Math.round(p.y) + ')';
      this.positionMsgOk = true;
      this.placing = null;
      await this.refreshPositions();
    },

    /* begin a drag of an already-placed marker. mousedown on the
       marker → mousemove on the svg updates the position visually →
       mouseup commits via PUT. */
    onMarkerMouseDown(event, kind, id) {
      if (!this.editPositions) return;
      event.preventDefault();
      event.stopPropagation();
      const svgEl = event.currentTarget.closest('svg');
      if (!svgEl) return;
      this._dragging = { kind, id: String(id), svgEl };
    },

    onPlanMouseMove(event) {
      if (!this._dragging) return;
      const p = this._svgPoint(event, this._dragging.svgEl);
      if (!p) return;
      // Live optimistic update so the marker tracks the cursor.
      if (!this.positions[this._dragging.kind]) this.positions[this._dragging.kind] = {};
      this.positions[this._dragging.kind][this._dragging.id] = { x: p.x, y: p.y };
    },

    async onPlanMouseUp(event) {
      if (!this._dragging) return;
      const drag = this._dragging;
      this._dragging = null;
      const p = this._svgPoint(event, drag.svgEl);
      if (!p) return;
      await this._putPosition(drag.kind, drag.id, p.x, p.y);
      await this.refreshPositions();
    },

    async _putPosition(kind, id, x, y) {
      try {
        const r = await fetch('/api/positions/' + kind + '/' + encodeURIComponent(id), {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ x, y }),
        });
        if (!r.ok) {
          const d = await r.json().catch(() => ({}));
          this.positionMsg = 'failed: ' + (d.detail || r.status);
          this.positionMsgOk = false;
        }
      } catch (e) {
        this.positionMsg = 'failed: ' + e;
        this.positionMsgOk = false;
      }
    },

    /* Marker rendering helpers — emoji icon + colour per kind so the
       floor plan reads at a glance. */
    markerIcon(kind) {
      return {
        station: '📺', light: '💡', display: '🟧',
        speaker: '🔊', microphone: '🎤',
      }[kind] || '•';
    },

    markerColor(kind) {
      // Hex literals only — bare SVG `fill="..."` attributes don't
      // reliably resolve `var(--…)` in all browsers (Chromium/Safari
      // quirks). Pick palette by hand so it survives any environment.
      return {
        station:    '#a100ff',  // brand purple
        light:      '#facc15',  // yellow
        display:    '#fb923c',  // orange
        speaker:    '#f87171',  // red
        microphone: '#c084fc',  // lavender
      }[kind] || '#888';
    },

    /* Iterate all placed markers as flat list. Used by the debug
       counter + the imperative renderMarkers below. */
    placedMarkers() {
      const out = [];
      for (const [kind, items] of Object.entries(this.positions || {})) {
        for (const [id, pos] of Object.entries(items || {})) {
          if (pos && typeof pos.x === 'number' && typeof pos.y === 'number') {
            out.push({ kind, id, x: pos.x, y: pos.y });
          }
        }
      }
      return out;
    },

    /* Imperative SVG marker creation. Alpine's `<template x-for>`
       doesn't reliably render into SVG namespace on some browsers,
       so we build the elements ourselves via createElementNS.
       Called by x-effect on the marker <g>; runs whenever positions
       or editPositions changes. */
    renderMarkers() {
      // Read the reactive deps so x-effect re-runs on changes.
      const markers = this.placedMarkers();
      const editing = this.editPositions;
      const layer = document.getElementById('device-markers');
      if (!layer) return;
      while (layer.firstChild) layer.removeChild(layer.firstChild);
      const NS = 'http://www.w3.org/2000/svg';
      for (const m of markers) {
        const g = document.createElementNS(NS, 'g');
        g.setAttribute('data-kind', m.kind);
        g.setAttribute('data-id', m.id);
        if (editing) g.style.cursor = 'grab';
        g.addEventListener('mousedown', (e) => {
          this.onMarkerMouseDown(e, m.kind, m.id);
        });

        const c = document.createElementNS(NS, 'circle');
        c.setAttribute('cx', m.x);
        c.setAttribute('cy', m.y);
        c.setAttribute('r', '18');
        c.setAttribute('fill', this.markerColor(m.kind));
        c.setAttribute('stroke', 'black');
        c.setAttribute('stroke-width', '2');
        g.appendChild(c);

        const icon = document.createElementNS(NS, 'text');
        icon.setAttribute('x', m.x);
        icon.setAttribute('y', m.y + 5);
        icon.setAttribute('text-anchor', 'middle');
        icon.setAttribute('style',
          'font-size:18px;pointer-events:none;user-select:none');
        icon.textContent = this.markerIcon(m.kind);
        g.appendChild(icon);

        const label = document.createElementNS(NS, 'text');
        label.setAttribute('x', m.x);
        label.setAttribute('y', m.y + 36);
        label.setAttribute('text-anchor', 'middle');
        // White text with a thin black stroke so labels read on any
        // background — works over zone fills, brand colours, etc.
        label.setAttribute('style',
          'font-size:11px;font-weight:bold;fill:#fff;'
          + 'stroke:rgba(0,0,0,0.85);stroke-width:0.6;paint-order:stroke;'
          + 'pointer-events:none;user-select:none');
        label.textContent = this.markerName(m.kind, m.id);
        g.appendChild(label);

        layer.appendChild(g);
      }
    },

    /* Name lookup for a placed marker, since we don't store names in
       positions.json — they come from the live placeables list. */
    markerName(kind, id) {
      const p = (this.placeables || []).find(x => x.kind === kind && x.id === String(id));
      return p ? p.name : (kind + ' ' + id);
    },
  };
}

window.studioShell = studioShell;
document.addEventListener('alpine:init', () => {
  Alpine.data('studioShell', studioShell);
});
