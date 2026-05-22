/* views/audio.js — Audio view.
 *
 * Mics are REAL (mDNS discovery + Sennheiser SSC control via
 * /api/audio/microphones/*). Sinks / sources / play_sound are still
 * stubs — the JSON panels just surface what the stub endpoints return
 * so the wiring is observable.
 */
function v2AudioView() {
  return {
    // Mics (real)
    mics: null,
    micsLoading: false,
    micsLastAction: '',
    micsLastOk: true,

    // Sinks / sources (stub)
    sinks: null,
    sources: null,

    async load() {
      await Promise.all([this.loadMics(), this.loadStubs()]);
    },

    async loadStubs() {
      try {
        const [sinksResp, sourcesResp] = await Promise.all([
          fetch('/api/audio/sinks').then(r => r.json()),
          fetch('/api/audio/sources').then(r => r.json()),
        ]);
        this.sinks = sinksResp;
        this.sources = sourcesResp;
      } catch (e) {
        console.error('audio stub load failed', e);
      }
    },

    async loadMics() {
      if (this.micsLoading) return;
      this.micsLoading = true;
      try {
        const r = await fetch('/api/audio/microphones');
        const d = await r.json();
        this.mics = d.microphones || [];
      } catch (e) {
        this.mics = [{ error: 'fetch failed: ' + e }];
      } finally {
        this.micsLoading = false;
      }
    },

    async muteMic(mic, muted) {
      this.micsLastAction = (muted ? 'muting ' : 'unmuting ') + (mic.friendly_name || mic.hostname) + '…';
      this.micsLastOk = true;
      try {
        const r = await fetch(
          '/api/audio/microphones/' + encodeURIComponent(mic.id) + '/mute',
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ muted: !!muted }),
          },
        );
        const d = await r.json();
        if (d.error) {
          this.micsLastAction = (muted ? 'mute' : 'unmute') + ' ✗ ' + d.error +
                                (d.detail ? (' — ' + d.detail) : '');
          this.micsLastOk = false;
        } else {
          this.micsLastAction = (muted ? 'mute' : 'unmute') + ' ✓ — HTTP ' + d.http_status;
          this.micsLastOk = d.http_status < 400;
        }
      } catch (e) {
        this.micsLastAction = (muted ? 'mute' : 'unmute') + ' ✗ ' + e;
        this.micsLastOk = false;
      }
    },
  };
}

window.v2AudioView = v2AudioView;
document.addEventListener('alpine:init', () => {
  Alpine.data('v2AudioView', v2AudioView);
});
