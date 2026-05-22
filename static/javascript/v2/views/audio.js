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

    // Network audio streams (Dante / AES67 via SAP, real)
    streams: null,
    streamsLoading: false,

    // Sinks / sources (stub)
    sinks: null,
    sources: null,

    async load() {
      await Promise.all([this.loadMics(), this.loadStubs(), this.loadStreams()]);
    },

    async loadStreams() {
      if (this.streamsLoading) return;
      this.streamsLoading = true;
      try {
        // The endpoint blocks ~5s while listening to SAP — set the
        // fetch up so the spinner shows the whole time.
        const r = await fetch('/api/audio/streams?timeout=5');
        const d = await r.json();
        this.streams = d.streams || [];
      } catch (e) {
        this.streams = [{ _error: 'fetch failed: ' + e }];
      } finally {
        this.streamsLoading = false;
      }
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

    async testMic(mic) {
      if (mic._testing) return;
      mic._testing = true;
      this.micsLastAction = 'reachability test ' + (mic.friendly_name || mic.hostname) + '…';
      this.micsLastOk = true;
      try {
        const r = await fetch(
          '/api/audio/microphones/' + encodeURIComponent(mic.id) + '/test',
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ probes: 3 }),
          },
        );
        const d = await r.json();
        if (d.error) {
          this.micsLastAction = 'test ✗ ' + d.error;
          this.micsLastOk = false;
        } else {
          const samples = d.samples || [];
          const latencies = samples
            .filter(s => s.latency_ms != null)
            .map(s => s.latency_ms);
          const avg = latencies.length
            ? (latencies.reduce((a, b) => a + b, 0) / latencies.length).toFixed(1)
            : '—';
          const codes = samples.map(s => s.http_status ?? 'err').join(', ');
          this.micsLastAction = `test ${d.ok ? '✓' : '✗'} — ${d.probes} probes, avg ${avg}ms, statuses [${codes}]`;
          this.micsLastOk = !!d.ok;
        }
      } catch (e) {
        this.micsLastAction = 'test ✗ ' + e;
        this.micsLastOk = false;
      } finally {
        mic._testing = false;
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
