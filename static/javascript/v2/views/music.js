/* views/music.js — Alpine.data factory for the Spotify-backed Music view.
 *
 * Talks to /api/music/* (which wraps the same spotify_client.call(...)
 * the MCP tools use). Until env vars land on the Pi, every endpoint
 * returns {"error": "spotify not configured", ...} and we render the
 * setup card. Once configured, the player + devices + search panels
 * appear and start polling.
 */
function v2MusicView() {
  return {
    configured: false,
    probeDetail: '',
    nowPlaying: null,
    devices: [],
    searchQuery: '',
    searchResults: [],
    lastAction: '',
    lastActionOk: true,
    testRunning: false,
    _timer: null,

    async init() {
      await this.checkStatus();
      if (this.configured) {
        await this.loadAll();
      }
      // Poll status periodically so the UI flips from "not configured"
      // to "ready" without needing a manual reload.
      this._timer = setInterval(() => this._tick(), 5000);
    },

    async _tick() {
      const wasConfigured = this.configured;
      await this.checkStatus();
      if (this.configured && !wasConfigured) {
        await this.loadAll();
      } else if (this.configured) {
        // Cheap refresh — devices + now-playing only.
        await this.loadNowPlaying();
      }
    },

    async checkStatus() {
      try {
        const r = await fetch('/api/music/status');
        const d = await r.json();
        this.configured = !!d.configured;
        if (!this.configured) {
          this.probeDetail = (d.probe && d.probe.detail) || '';
        }
      } catch (e) {
        this.configured = false;
        this.probeDetail = 'probe failed: ' + e;
      }
    },

    async loadAll() {
      await Promise.all([this.loadNowPlaying(), this.loadDevices()]);
    },

    async loadNowPlaying() {
      try {
        const r = await fetch('/api/music/now_playing');
        const d = await r.json();
        if (d.ok) this.nowPlaying = d.data; else this.nowPlaying = null;
      } catch (e) { this.nowPlaying = null; }
    },

    async loadDevices() {
      try {
        const r = await fetch('/api/music/devices');
        const d = await r.json();
        this.devices = (d.ok && d.data && d.data.devices) ? d.data.devices : [];
      } catch (e) { this.devices = []; }
    },

    /* ---------- transport ---------- */

    async togglePlay() {
      if (!this.nowPlaying) return this.play(null);
      if (this.nowPlaying.is_playing) await this._postJSON('/api/music/pause', {});
      else await this._postJSON('/api/music/play', {});
      await this.loadNowPlaying();
    },

    async play(uri) {
      const r = await this._postJSON('/api/music/play', uri ? { uri } : {});
      this._toast(r, 'play');
      await this.loadNowPlaying();
    },

    async pause() {
      const r = await this._postJSON('/api/music/pause', {});
      this._toast(r, 'pause');
      await this.loadNowPlaying();
    },

    async next() {
      const r = await this._postJSON('/api/music/next', {});
      this._toast(r, 'next');
      await this.loadNowPlaying();
    },

    async previous() {
      const r = await this._postJSON('/api/music/previous', {});
      this._toast(r, 'previous');
      await this.loadNowPlaying();
    },

    async setVolume(pct) {
      const r = await this._postJSON('/api/music/volume', { volume_pct: parseInt(pct) });
      this._toast(r, 'volume');
      await this.loadDevices();
    },

    async transferTo(device) {
      // Spotify "transfer playback" isn't a separate endpoint here —
      // starting playback with device_id implicitly transfers.
      const r = await this._postJSON('/api/music/play', { device_id: device.id });
      this._toast(r, 'transfer to ' + device.name);
      await this.loadAll();
    },

    /* ---------- search ---------- */

    async search() {
      const q = (this.searchQuery || '').trim();
      if (!q) { this.searchResults = []; return; }
      try {
        const r = await fetch('/api/music/search?q=' + encodeURIComponent(q));
        const d = await r.json();
        this.searchResults = (d.ok && d.data && d.data.tracks && d.data.tracks.items) || [];
      } catch (e) {
        this.searchResults = [];
        this.lastAction = 'search failed: ' + e;
        this.lastActionOk = false;
      }
    },

    /* ---------- speaker test ---------- */

    async runSpeakerTest() {
      if (this.testRunning) return;
      this.testRunning = true;
      this.lastAction = 'speaker test running… (Hotel California on Bose, 20%, 20s)';
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
        } else {
          const dev = d.device?.name || d.device_query;
          const track = d.track?.label || d.track_query;
          this.lastAction = `speaker test ✓ — played ${d.play_seconds}s of "${track}" on ${dev}`;
          this.lastActionOk = !!d.playback_started;
        }
      } catch (e) {
        this.lastAction = 'speaker test ✗ ' + e;
        this.lastActionOk = false;
      } finally {
        this.testRunning = false;
        await this.loadAll();
      }
    },

    /* ---------- helpers ---------- */

    async _postJSON(url, body) {
      try {
        const r = await fetch(url, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body || {}),
        });
        return await r.json();
      } catch (e) {
        return { error: 'fetch_failed', detail: String(e) };
      }
    },

    _toast(resp, label) {
      if (resp && resp.error) {
        this.lastAction = label + ' ✗ ' + resp.error;
        this.lastActionOk = false;
      } else {
        this.lastAction = label + ' ✓';
        this.lastActionOk = true;
      }
    },
  };
}

window.v2MusicView = v2MusicView;
document.addEventListener('alpine:init', () => {
  Alpine.data('v2MusicView', v2MusicView);
});
