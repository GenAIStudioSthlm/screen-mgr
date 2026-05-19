/* shell.js — Alpine x-data factory for the /admin/v2 layout.
 *
 * Responsibilities:
 *   - Holds the list of zones (polled from /api/zones every 8s)
 *   - Holds the currently selected zone
 *   - Holds the active sidebar view ('screens' | 'lighting' | 'led_screens' | 'modules')
 *   - Runs the header clock
 *
 * Stays small on purpose. Per-domain logic (light controls, screen content,
 * LED service, modules registry) lives in views/<name>.js, each managing
 * its own Alpine sub-scope. The shell never reaches into a view.
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
      await this.refreshZones();
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
