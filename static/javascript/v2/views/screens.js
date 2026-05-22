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
    testRunning: false,
    _timer: null,
    _lastSelectedScreenId: null,

    // Media libraries (populated by _loadMedia)
    videos: [],
    pdfs: [],
    slideshows: [],
    pictures: {},        // { folder: [filename, ...] }
    pictureOptions: [],  // flattened [{ value: 'folder/file' | 'file', label, folder }]

    // Upload UI state
    uploadMsg: '',
    uploadOk: true,
    pictureSubfolder: '',
    pictureNewSubfolder: '',

    async load() {
      await Promise.all([
        this._loadScreens(),
        this._loadModules(),
        this._loadMedia(),
      ]);
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
    async _loadMedia() {
      try {
        const [v, p, pd, ss] = await Promise.all([
          fetch('/api/videos').then(r => r.json()),
          fetch('/api/pictures').then(r => r.json()),
          fetch('/api/pdfs').then(r => r.json()),
          fetch('/api/slideshows').then(r => r.json()),
        ]);
        this.videos = v.videos || [];
        this.pdfs = pd.pdfs || [];
        this.slideshows = ss.slideshows || [];
        this.pictures = p.pictures || {};
        // Flatten pictures into an options list with stable "folder/file" values.
        // "Root" (top-level) entries use just the filename as value to match how
        // the legacy admin stored them in screens.json.
        const opts = [];
        Object.keys(this.pictures).sort().forEach(folder => {
          (this.pictures[folder] || []).slice().sort().forEach(file => {
            const value = folder === 'Root' ? file : (folder + '/' + file);
            opts.push({ value, label: file, folder });
          });
        });
        this.pictureOptions = opts;
      } catch (e) { console.error('media load failed', e); }
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
        case 'url': return 'https://example.com  (YouTube URLs auto-embed)';
        case 'screen_share': return 'room-id';
        default: return '';
      }
    },

    pictureSubfolders() {
      // Folders we can upload INTO. "Root" maps to the empty string on POST.
      return Object.keys(this.pictures).sort();
    },

    async uploadMedia(kind, fileInputEl) {
      const file = fileInputEl?.files?.[0];
      if (!file) {
        this.uploadMsg = 'no file selected';
        this.uploadOk = false;
        return;
      }
      this.uploadMsg = 'uploading ' + file.name + '…';
      this.uploadOk = true;
      const fd = new FormData();
      fd.append('file', file);
      let endpoint;
      if (kind === 'video')   endpoint = '/api/upload/video';
      else if (kind === 'pdf')     endpoint = '/api/upload/pdf';
      else if (kind === 'picture') {
        endpoint = '/api/upload/picture';
        const sf = (this.pictureNewSubfolder || this.pictureSubfolder || '').trim();
        if (sf) fd.append('subfolder', sf);
      } else {
        this.uploadMsg = 'unknown kind: ' + kind;
        this.uploadOk = false;
        return;
      }
      try {
        const r = await fetch(endpoint, { method: 'POST', body: fd });
        const d = await r.json();
        if (r.ok) {
          this.uploadMsg = 'uploaded ' + (d.path || file.name) + ' ✓';
          this.uploadOk = true;
          fileInputEl.value = '';
          this.pictureNewSubfolder = '';
          await this._loadMedia();
          // If the active editor is for this kind, auto-select the just-uploaded file.
          if (kind === 'picture' && this.editing.type === 'picture') {
            this.editing.value = d.path || file.name;
          } else if (kind === 'video' && this.editing.type === 'video') {
            this.editing.value = file.name;
          } else if (kind === 'pdf' && this.editing.type === 'pdf') {
            this.editing.value = file.name;
          }
        } else {
          this.uploadMsg = 'failed: ' + (d.detail || JSON.stringify(d));
          this.uploadOk = false;
        }
      } catch (e) {
        this.uploadMsg = 'failed: ' + e;
        this.uploadOk = false;
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

    /* Fleet demo: cycle every available screen through URL web → URL
     * YouTube → default → settle on the AI News scene. Long-running
     * (~20s) — disable the button while in flight, surface a one-line
     * result when done. */
    async runFleetDemo() {
      if (this.testRunning) return;
      this.testRunning = true;
      this.lastAction = 'fleet demo running… (~20s)';
      this.lastActionOk = true;
      try {
        const r = await fetch('/api/screens/run_fleet_demo', { method: 'POST' });
        const d = await r.json();
        if (r.ok) {
          const targets = (d.targets || []).length;
          const source = d.target_source || '?';
          const reloaded = (d.settle_result?.reloaded || []).length;
          const settle = d.settle_scene_id || '?';
          this.lastAction = `fleet demo ✓ — ${targets} target screens (${source}), settled on '${settle}' (${reloaded} reloaded)`;
          this.lastActionOk = true;
        } else {
          this.lastAction = 'fleet demo ✗ ' + (d.detail || JSON.stringify(d));
          this.lastActionOk = false;
        }
      } catch (e) {
        this.lastAction = 'fleet demo ✗ ' + e;
        this.lastActionOk = false;
      } finally {
        this.testRunning = false;
        await this._loadScreens();
      }
    },
  };
}

window.v2ScreensView = v2ScreensView;
document.addEventListener('alpine:init', () => {
  Alpine.data('v2ScreensView', v2ScreensView);
});
