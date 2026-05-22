/* views/audio.js — Audio view (stub backend today).
 *
 * Surfaces what the /api/audio/* endpoints return so we can see the
 * stub responses + tell at a glance whether real wiring has landed.
 * When the backend swap happens, the JSON renders real device lists
 * with no template changes.
 */
function v2AudioView() {
  return {
    sinks: null,
    sources: null,
    _timer: null,

    async load() {
      try {
        const [sinksResp, sourcesResp] = await Promise.all([
          fetch('/api/audio/sinks').then(r => r.json()),
          fetch('/api/audio/sources').then(r => r.json()),
        ]);
        this.sinks = sinksResp;
        this.sources = sourcesResp;
      } catch (e) {
        console.error('audio load failed', e);
      }
      // No auto-refresh while the backend is a stub — refresh button is enough.
    },
  };
}

window.v2AudioView = v2AudioView;
document.addEventListener('alpine:init', () => {
  Alpine.data('v2AudioView', v2AudioView);
});
