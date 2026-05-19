/* views/led_screens.js — Alpine factory for the LED Screens view.
 *
 * Surfaces every LED-screen service module. Today: just rgbdisplay
 * (the 32x64 LED matrix). Future modules (a second matrix, an LED
 * strip controller, etc.) appear automatically because we filter
 * /api/modules by id and not by hard-coded names.
 */
function v2LedScreensView() {
  // List of module ids we treat as LED screens. Adding to this list
  // surfaces a new card with the same Start/Stop UX.
  const LED_MODULE_IDS = ['rgbdisplay'];

  return {
    panels: [],
    _timer: null,

    async load() {
      try {
        const r = await fetch('/api/modules');
        const d = await r.json();
        const prev = Object.fromEntries(this.panels.map(p => [p.id, p]));
        this.panels = (d.modules || [])
          .filter(m => LED_MODULE_IDS.includes(m.id))
          .map(m => ({
            ...m,
            lastAction: prev[m.id]?.lastAction || '',
            lastActionOk: prev[m.id]?.lastActionOk ?? true,
          }));
      } catch (e) { console.error('led_screens load failed', e); }
      clearTimeout(this._timer);
      this._timer = setTimeout(() => this.load(), 5000);
    },

    async toggleEnabled(panel) {
      const path = panel.enabled ? 'disable' : 'enable';
      try { await fetch('/api/modules/' + panel.id + '/' + path, { method: 'POST' }); }
      catch (e) { console.error('toggle failed', e); }
      await this.load();
    },

    async action(panel, name) {
      panel.lastAction = name + '…';
      panel.lastActionOk = true;
      try {
        const r = await fetch('/api/modules/' + panel.id + '/' + name, { method: 'POST' });
        const d = await r.json();
        panel.lastAction = name + ' ' + (d.ok ? '✓' : '✗') + (d.stderr ? (' ' + d.stderr) : '');
        panel.lastActionOk = !!d.ok;
      } catch (e) {
        panel.lastAction = name + ' ✗ ' + e;
        panel.lastActionOk = false;
      }
      await this.load();
    },
  };
}

window.v2LedScreensView = v2LedScreensView;
