/* shell.js — Alpine x-data factory for the /admin/v2 layout.
 *
 * Registered as Alpine data on the `alpine:init` event, which fires
 * before Alpine processes any x-data attribute. This avoids the
 * timing/scope quirks of relying on `window.studioShell` being set
 * before Alpine evaluates `<body x-data="studioShell()">`.
 */
document.addEventListener('alpine:init', () => {
  Alpine.data('studioShell', () => ({
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
  }));

  console.log('[studio v2] shell registered');
});
