/* views/led_screens.js — Alpine.data factory for the LED Screens view.
 *
 * Surfaces every LED-screen service module. Today: just rgbdisplay
 * (the 32x64 LED matrix). Future modules appear automatically because
 * we filter /api/modules by id and not by hard-coded names.
 */
const LED_MODULE_IDS = ['rgbdisplay'];

function v2LedScreensView() {
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
            testRunning: prev[m.id]?.testRunning || false,
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

    /* Run the grid test pattern for ~15s then revert. Long-running:
     * disables the button while in flight; surfaces a one-line result. */
    async runTestPattern(panel) {
      if (panel.testRunning) return;
      panel.testRunning = true;
      panel.lastAction = 'test pattern running… (~15s)';
      panel.lastActionOk = true;
      try {
        const r = await fetch(
          '/api/modules/' + panel.id + '/run_test_pattern',
          { method: 'POST' },
        );
        const d = await r.json();
        if (r.ok) {
          panel.lastAction = 'test ✓ — ran ' + d.duration_seconds + 's, reverted to clock';
          panel.lastActionOk = !!d.ok;
        } else {
          panel.lastAction = 'test ✗ ' + (d.detail || JSON.stringify(d));
          panel.lastActionOk = false;
        }
      } catch (e) {
        panel.lastAction = 'test ✗ ' + e;
        panel.lastActionOk = false;
      } finally {
        panel.testRunning = false;
        await this.load();
      }
    },
  };
}

window.v2LedScreensView = v2LedScreensView;
document.addEventListener('alpine:init', () => {
  Alpine.data('v2LedScreensView', v2LedScreensView);
});
