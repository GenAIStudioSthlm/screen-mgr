/* views/music.js — Music view (embedded Spotify Web Player + speaker test).
 *
 * The view embeds open.spotify.com so anyone can sign in with their
 * own (or the enterprise) account; Spotify handles its own auth in
 * the iframe. No server-side credentials needed for everyday play.
 *
 * Server-side Spotify creds (.env on the Pi) are only required for
 * the "Run speaker test" button — that calls /api/music/speaker_test
 * which routes through `mcps.music.spotify_client`. The configured
 * flag drives a small inline nudge under the header when creds are
 * missing.
 */
function v2MusicView() {
  return {
    configured: false,
    probeDetail: '',
    lastAction: '',
    lastActionOk: true,
    testRunning: false,
    presets: [],
    playingPresetId: null,
    _timer: null,

    async init() {
      await this.checkStatus();
      await this.loadPresets();
      // Poll status every 30s so the nudge disappears automatically
      // once .env is filled in — no manual reload needed.
      this._timer = setInterval(() => this.checkStatus(), 30000);
    },

    async loadPresets() {
      try {
        const r = await fetch('/api/music/presets');
        const d = await r.json();
        this.presets = d.presets || [];
      } catch (e) {
        this.presets = [];
      }
    },

    async playPreset(preset) {
      if (this.playingPresetId) return;
      this.playingPresetId = preset.id;
      this.lastAction = `${preset.icon || ''} ${preset.name} → ${preset.device_query} …`.trim();
      this.lastActionOk = true;
      try {
        const r = await fetch(
          '/api/music/presets/' + encodeURIComponent(preset.id) + '/play',
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: '{}',
          },
        );
        const d = await r.json();
        if (d.error) {
          this.lastAction = preset.name + ' ✗ ' + d.error + (d.detail ? (' — ' + d.detail) : '') + (d.hint ? (' — ' + d.hint) : '');
          this.lastActionOk = false;
        } else if (d.playback_started) {
          const dev = d.device?.name || preset.device_query;
          const target = d.target?.label || preset.search_query;
          this.lastAction = `${preset.name} ✓ — playing "${target}" on ${dev} @ ${d.volume_pct}%`;
          this.lastActionOk = true;
        } else {
          this.lastAction = preset.name + ' ✗ playback did not start';
          this.lastActionOk = false;
        }
      } catch (e) {
        this.lastAction = preset.name + ' ✗ ' + e;
        this.lastActionOk = false;
      } finally {
        this.playingPresetId = null;
      }
    },

    async checkStatus() {
      try {
        const r = await fetch('/api/music/status');
        const d = await r.json();
        this.configured = !!d.configured;
        this.probeDetail = (!this.configured && d.probe && d.probe.detail) || '';
      } catch (e) {
        this.configured = false;
        this.probeDetail = 'probe failed: ' + e;
      }
    },

    async runSpeakerTest() {
      if (this.testRunning) return;
      this.testRunning = true;
      this.lastAction = 'speaker test running… (Hotel California on MarantzCinema70s, 20%, 20s)';
      this.lastActionOk = true;
      try {
        const r = await fetch('/api/music/speaker_test', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: '{}',
        });
        const d = await r.json();
        if (d.error) {
          this.lastAction = 'speaker test ✗ ' + d.error + (d.detail ? (' — ' + d.detail) : '');
          this.lastActionOk = false;
        } else if (!d.playback_started) {
          // e.g. device not visible
          this.lastAction = 'speaker test ✗ ' + (d.error || 'playback did not start') +
                            (d.hint ? (' — ' + d.hint) : '');
          this.lastActionOk = false;
        } else {
          const dev = d.device?.name || d.device_query;
          const track = d.track?.label || d.track_query;
          this.lastAction = `speaker test ✓ — played ${d.play_seconds}s of "${track}" on ${dev}`;
          this.lastActionOk = true;
        }
      } catch (e) {
        this.lastAction = 'speaker test ✗ ' + e;
        this.lastActionOk = false;
      } finally {
        this.testRunning = false;
      }
    },
  };
}

window.v2MusicView = v2MusicView;
document.addEventListener('alpine:init', () => {
  Alpine.data('v2MusicView', v2MusicView);
});
