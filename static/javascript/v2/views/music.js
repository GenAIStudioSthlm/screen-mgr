/* views/music.js — Music view (embedded Spotify Web Player + Marantz test).
 *
 * The Spotify side is just the iframe — anyone signs in inside it,
 * Spotify handles its own auth. No backend OAuth needed for everyday
 * play.
 *
 * The Marantz test fires a controlled local-file playback through HEOS:
 * lunchroombeating.mp3 at level 40 (capped under 70 safety ceiling)
 * for 4 seconds with auto-stop. Plus a kill-switch Stop button that
 * sends `set_play_state=stop` to the AVR regardless of what's playing.
 */
function v2MusicView() {
  return {
    // Marantz test
    marantzTesting: false,
    marantzAction: '',
    marantzActionOk: true,

    init() {
      // Nothing to load on startup — iframe handles Spotify, Marantz
      // calls are user-triggered. Kept as a hook for future re-enable
      // of presets / now-playing polling if Path B ever turns on.
    },

    async runMarantzTest() {
      if (this.marantzTesting) return;
      this.marantzTesting = true;
      this.marantzAction = 'Marantz test running… (lunchroombeating.mp3, fade 20→50 over 2 s, then 4 s play)';
      this.marantzActionOk = true;
      try {
        const r = await fetch('/api/music/marantz/play_local_file', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            file_path: 'lunchroombeating.mp3',
            volume_pct: 50,
            duration_seconds: 4,
            ramp_seconds: 2,
            ramp_from: 20,
          }),
        });
        const d = await r.json();
        if (d.error) {
          this.marantzAction = 'test ✗ ' + d.error + (d.detail ? (' — ' + d.detail) : '');
          this.marantzActionOk = false;
        } else if (d.playback_started) {
          const hint = d.calibration_hint ? ` (${d.calibration_hint.split(' — ')[0]})` : '';
          const ramp = d.ramp_from != null
            ? ` — fade ${d.ramp_from}→${d.volume_pct} over ${d.ramp_seconds}s`
            : '';
          this.marantzAction = `test ✓ — played ${d.file} @ ${d.volume_pct}${hint}${ramp}, auto-stopped after ${d.duration_seconds}s`;
          this.marantzActionOk = true;
        } else {
          this.marantzAction = 'test ✗ playback did not start';
          this.marantzActionOk = false;
        }
      } catch (e) {
        this.marantzAction = 'test ✗ ' + e;
        this.marantzActionOk = false;
      } finally {
        this.marantzTesting = false;
      }
    },

    async stopMarantz() {
      this.marantzAction = 'sending stop…';
      this.marantzActionOk = true;
      try {
        const r = await fetch('/api/music/marantz/stop', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: '{}',
        });
        const d = await r.json();
        if (d.error) {
          this.marantzAction = 'stop ✗ ' + d.error + (d.detail ? (' — ' + d.detail) : '');
          this.marantzActionOk = false;
        } else {
          this.marantzAction = 'stop ✓';
          this.marantzActionOk = true;
        }
      } catch (e) {
        this.marantzAction = 'stop ✗ ' + e;
        this.marantzActionOk = false;
      }
    },
  };
}

window.v2MusicView = v2MusicView;
document.addEventListener('alpine:init', () => {
  Alpine.data('v2MusicView', v2MusicView);
});
