/* views/audio.js — Audio view.
 *
 * All real:
 *   • PulseAudio sinks/sources/volume/mute via /api/audio/{sinks,sources,volume,mute}
 *   • Networked mics via mDNS discovery + Sennheiser SSC reachability probe
 *   • Network audio streams (Dante / AES67) via SAP listener
 */
function v2AudioView() {
  return {
    // System sinks (PulseAudio)
    sinks: null,
    sources: null,
    defaultSink: '',
    sinksLoading: false,
    sinkAction: '',
    sinkActionOk: true,

    // Mics (Sennheiser SSC via mDNS)
    mics: null,
    micsLoading: false,
    micsLastAction: '',
    micsLastOk: true,

    // Network audio streams (Dante / AES67 via SAP)
    streams: null,
    streamsLoading: false,

    async load() {
      await Promise.all([
        this.loadSinks(),
        this.loadMics(),
        this.loadStreams(),
      ]);
    },

    async loadSinks() {
      if (this.sinksLoading) return;
      this.sinksLoading = true;
      try {
        const [sinksResp, sourcesResp] = await Promise.all([
          fetch('/api/audio/sinks').then(r => r.json()),
          fetch('/api/audio/sources').then(r => r.json()),
        ]);
        this.sinks = sinksResp;
        this.sources = sourcesResp;
        this.defaultSink = sinksResp?.default_sink || '';
      } catch (e) {
        this.sinks = { error: 'fetch failed: ' + e };
      } finally {
        this.sinksLoading = false;
      }
    },

    async setSinkVolume(sink, pct) {
      this.sinkAction = sink.name + ' → ' + pct + '%…';
      this.sinkActionOk = true;
      try {
        const r = await fetch('/api/audio/volume', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ sink_id: sink.name, volume_pct: parseInt(pct) }),
        });
        const d = await r.json();
        if (d.error) {
          this.sinkAction = sink.name + ' ✗ ' + d.error;
          this.sinkActionOk = false;
        } else {
          this.sinkAction = sink.name + ' ✓ — ' + d.volume_pct + '%';
          this.sinkActionOk = !!d.ok;
        }
      } catch (e) {
        this.sinkAction = sink.name + ' ✗ ' + e;
        this.sinkActionOk = false;
      }
      await this.loadSinks();
    },

    async toggleMute(sink) {
      const want = !sink.muted;
      this.sinkAction = (want ? 'muting ' : 'unmuting ') + sink.name + '…';
      this.sinkActionOk = true;
      try {
        const r = await fetch('/api/audio/mute', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ sink_id: sink.name, muted: want }),
        });
        const d = await r.json();
        if (d.error) {
          this.sinkAction = sink.name + ' ✗ ' + d.error;
          this.sinkActionOk = false;
        } else {
          this.sinkAction = sink.name + ' ✓ — muted=' + d.muted;
          this.sinkActionOk = !!d.ok;
        }
      } catch (e) {
        this.sinkAction = sink.name + ' ✗ ' + e;
        this.sinkActionOk = false;
      }
      await this.loadSinks();
    },

    /* ---------- streams ---------- */

    async loadStreams() {
      if (this.streamsLoading) return;
      this.streamsLoading = true;
      try {
        const r = await fetch('/api/audio/streams?timeout=5');
        const d = await r.json();
        this.streams = d.streams || [];
      } catch (e) {
        this.streams = [{ _error: 'fetch failed: ' + e }];
      } finally {
        this.streamsLoading = false;
      }
    },

    /* ---------- mics ---------- */

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
          this.micsLastAction = (muted ? 'mute' : 'unmute') + ' ✗ ' + d.error;
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
