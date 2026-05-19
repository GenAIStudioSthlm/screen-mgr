/* views/modules.js — Alpine factory for the v2 Modules view.
 *
 * Self-contained: polls /api/modules every 5s, supports enable/disable,
 * Start/Stop for service modules, and the full add/refresh/delete flow
 * for external modules. Identical functionality to the legacy admin
 * Modules tab, restyled with the v2 design tokens.
 */
function v2ModulesView() {
  return {
    modules: [],
    newManifestUrl: '',
    lastExternal: '',
    lastExternalOk: true,
    showAdd: false,
    showHelp: false,
    copied: '',
    _timer: null,

    async load() {
      try {
        const r = await fetch('/api/modules');
        const d = await r.json();
        const prev = Object.fromEntries(this.modules.map(m => [m.id, m]));
        this.modules = (d.modules || []).map(m => ({
          ...m,
          lastAction: prev[m.id]?.lastAction || '',
          lastActionOk: prev[m.id]?.lastActionOk ?? true,
        }));
      } catch (e) {
        console.error('modules load failed', e);
      }
      clearTimeout(this._timer);
      this._timer = setTimeout(() => this.load(), 5000);
    },

    async toggleEnabled(m) {
      const path = m.enabled ? 'disable' : 'enable';
      try {
        await fetch('/api/modules/' + m.id + '/' + path, { method: 'POST' });
      } catch (e) { console.error('toggle failed', e); }
      await this.load();
    },

    async action(m, name) {
      m.lastAction = name + '…';
      m.lastActionOk = true;
      try {
        const r = await fetch('/api/modules/' + m.id + '/' + name, { method: 'POST' });
        const d = await r.json();
        m.lastAction = name + ' ' + (d.ok ? '✓' : '✗') + (d.stderr ? (' ' + d.stderr) : '');
        m.lastActionOk = !!d.ok;
      } catch (e) {
        m.lastAction = name + ' ✗ ' + e;
        m.lastActionOk = false;
      }
      await this.load();
    },

    async addExternal() {
      const url = (this.newManifestUrl || '').trim();
      if (!url) return;
      this.lastExternal = 'registering ' + url + '…';
      this.lastExternalOk = true;
      try {
        const r = await fetch('/api/modules/external', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ manifest_url: url }),
        });
        const d = await r.json();
        if (r.ok) {
          this.lastExternal = 'registered ' + (d.id || url) + ' ✓';
          this.lastExternalOk = true;
          this.newManifestUrl = '';
        } else {
          this.lastExternal = 'failed: ' + (d.detail || JSON.stringify(d));
          this.lastExternalOk = false;
        }
      } catch (e) {
        this.lastExternal = 'failed: ' + e;
        this.lastExternalOk = false;
      }
      await this.load();
    },

    async removeExternal(m) {
      if (!confirm('Remove external module "' + m.id + '"?')) return;
      try {
        await fetch('/api/modules/external/' + encodeURIComponent(m.id), { method: 'DELETE' });
      } catch (e) { console.error('remove external failed', e); }
      await this.load();
    },

    async refreshExternals() {
      this.lastExternal = 'refreshing all external manifests…';
      this.lastExternalOk = true;
      try {
        const r = await fetch('/api/modules/refresh', { method: 'POST' });
        const d = await r.json();
        const ok = (d.results || []).filter(x => x.ok).length;
        const total = (d.results || []).length;
        this.lastExternal = 'refreshed ' + ok + '/' + total;
        this.lastExternalOk = ok === total;
      } catch (e) {
        this.lastExternal = 'failed: ' + e;
        this.lastExternalOk = false;
      }
      await this.load();
    },

    async copyText(text, key) {
      try {
        await navigator.clipboard.writeText(text);
        this.copied = key;
        setTimeout(() => { if (this.copied === key) this.copied = ''; }, 1500);
      } catch (e) { console.error('clipboard write failed', e); }
    },
  };
}

window.v2ModulesView = v2ModulesView;
