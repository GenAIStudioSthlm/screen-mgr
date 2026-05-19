/* views/screens.js — Alpine.data factory for the v2 Screens view.
 *
 * Per-zone screen content editor + global screen list with reload-all.
 * Reads the shell's selected zone via Alpine scope chain.
 */
function v2ScreensView() {
  return {
    screens: [],
    displayModules: [],
    editing: { type: '', value: '', news_mode: 'landscape' },
    lastAction: '',
    lastActionOk: true,
    _timer: null,
    _lastSelectedScreenId: null,

    async load() {
      await Promise.all([this._loadScreens(), this._loadModules()]);
      clearTimeout(this._timer);
      this._timer = setTimeout(() => this.load(), 6000);
    },
    async _loadScreens() {
      try {
        const r = await fetch('/api/screens');
        const d = await r.json();
        this.screens = d.screens || [];
      } catch (e) { console.error('screens load failed', e); }
    },
    async _loadModules() {
      try {
        const r = await fetch('/api/modules');
        const d = await r.json();
        this.displayModules = (d.modules || []).filter(m =>
          m.type.includes('display') && m.enabled
        );
      } catch (e) { console.error('modules load failed', e); }
    },

    screenFor(zone) {
      if (!zone?.screen_id) return null;
      return this.screens.find(s => s.id === zone.screen_id) || null;
    },

    syncEditor(zone) {
      const s = this.screenFor(zone);
      if (!s) {
        this._lastSelectedScreenId = null;
        this.editing = { type: '', value: '', news_mode: 'landscape' };
        return;
      }
      if (this._lastSelectedScreenId === s.id) return;
      this._lastSelectedScreenId = s.id;
      this.editing = {
        type: s.type,
        value: this._valueFor(s, s.type),
        news_mode: s.news_mode || 'landscape',
      };
    },
    _valueFor(s, type) {
      switch (type) {
        case 'text': return s.text || '';
        case 'url': return s.url || '';
        case 'video': return s.video || '';
        case 'picture': return s.picture || '';
        case 'pdf': return s.pdf || '';
        case 'slideshow': return s.slideshow || '';
        case 'screen_share': return s.screen_share || '';
        default: return '';
      }
    },
    _placeholderFor(type) {
      switch (type) {
        case 'text': return 'Hello world';
        case 'url': return 'https://example.com';
        case 'video': return 'video.mp4 (must already be uploaded)';
        case 'picture': return 'subfolder/image.jpg (must already be uploaded)';
        case 'pdf': return 'doc.pdf (must already be uploaded)';
        case 'slideshow': return 'subfolder (must already exist under static/pictures)';
        case 'screen_share': return 'room-id';
        default: return '(no value needed)';
      }
    },

    async save(zone) {
      const s = this.screenFor(zone);
      if (!s) return;
      this.lastAction = 'saving…';
      this.lastActionOk = true;
      try {
        const body = new URLSearchParams();
        body.append('content_type', this.editing.type);
        body.append('content_value', this.editing.type === 'news' ? this.editing.news_mode : (this.editing.value || ''));
        const r = await fetch('/api/screens/' + s.id + '/set_content', {
          method: 'POST',
          headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
          body: body.toString(),
        });
        const d = await r.json();
        if (r.ok) {
          this.lastAction = 'saved';
          this.lastActionOk = true;
        } else {
          this.lastAction = 'failed: ' + (d.detail || JSON.stringify(d));
          this.lastActionOk = false;
        }
      } catch (e) {
        this.lastAction = 'failed: ' + e;
        this.lastActionOk = false;
      }
      this._lastSelectedScreenId = null;
      await this._loadScreens();
      this.syncEditor(zone);
    },

    async reloadAll() {
      this.lastAction = 'reloading all…';
      this.lastActionOk = true;
      try {
        const r = await fetch('/api/screens/reload-all', { method: 'POST' });
        const d = await r.json();
        this.lastAction = 'notified ' + (d.notified || []).length + ' / ' + d.total;
        this.lastActionOk = true;
      } catch (e) {
        this.lastAction = 'failed: ' + e;
        this.lastActionOk = false;
      }
    },
  };
}

window.v2ScreensView = v2ScreensView;
document.addEventListener('alpine:init', () => {
  Alpine.data('v2ScreensView', v2ScreensView);
});
