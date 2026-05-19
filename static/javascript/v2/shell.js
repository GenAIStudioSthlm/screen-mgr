console.log('[studio v2] shell.js LOADED');
/* shell.js — Alpine x-data factory for the /admin/v2 layout.
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

    async load() {
      this.startClock();
      await Promise.all([this.refreshZones(), this.refreshScenes()]);
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
  };
}

window.studioShell = studioShell;
document.addEventListener('alpine:init', () => {
  Alpine.data('studioShell', studioShell);
  console.log('[studio v2] shell registered');
});
