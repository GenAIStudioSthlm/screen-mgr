/* views/music.js — Music view (Path A: embedded Spotify Web Player only).
 *
 * The view is intentionally minimal: an iframe to open.spotify.com and
 * a fallback "open in new tab" button. Everyone signs in with their
 * own (or the enterprise) Spotify account inside the iframe; Spotify
 * handles its own auth.
 *
 * The `/api/music/*` HTTP endpoints + the Music MCP tools (presets,
 * speaker_test, transport) stay in the backend for the day the studio
 * decides to enable Path B (server-side OAuth). No JS state needed
 * here — the iframe owns the player.
 */
function v2MusicView() {
  return {
    init() {
      // Intentionally empty — nothing to load. Kept as a hook so
      // future Path B re-enabling has a place to wire status polling
      // back in without touching the template's x-data attribute.
    },
  };
}

window.v2MusicView = v2MusicView;
document.addEventListener('alpine:init', () => {
  Alpine.data('v2MusicView', v2MusicView);
});
