/* views/chat.js — Alpine.data factory for the right-panel agent chat.
 *
 * POSTs /api/chat and reads back an SSE stream (event-stream over
 * fetch+ReadableStream — EventSource only supports GET, which doesn't
 * fit our message-list payload). Today the endpoint is a stub that
 * always emits one `error` event with a not-implemented message; the
 * frontend code is written against the final event contract so the
 * backend can land later without changing this file.
 *
 * Voice: push-to-talk via the on-screen 🎤 button (mouse/touch hold)
 * OR the spacebar when the chat textarea is NOT focused. Uses the
 * Web Speech API directly — final transcript fills the input and
 * sends automatically. Browsers without SpeechRecognition (Safari /
 * Firefox) gracefully hide the voice affordance.
 */
function v2ChatView() {
  return {
    messages: [],            // [{role: 'user' | 'assistant' | 'error', content}]
    input: '',
    sending: false,
    sessionId: '',
    backendReady: false,     // flipped true when the stub goes away

    // Voice
    voiceSupported: false,
    voiceListening: false,
    voiceTranscript: '',
    _recognition: null,
    _spaceDown: false,

    init() {
      // One session id per browser tab. The plan accepts per-tab
      // sessions for v1; no cross-tab sharing.
      this.sessionId = crypto.randomUUID ? crypto.randomUUID() : ('tab-' + Date.now());
      this._initVoice();
      this._initSpaceShortcut();
    },

    /* ---------- send + stream ---------- */

    async send(textOverride) {
      const text = (textOverride !== undefined ? textOverride : this.input).trim();
      if (!text || this.sending) return;
      this.input = '';
      this.voiceTranscript = '';
      this.messages.push({ role: 'user', content: text });
      this._scrollToBottom();
      this.sending = true;

      try {
        const resp = await fetch('/api/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            session_id: this.sessionId,
            messages: this.messages
              .filter(m => m.role === 'user' || m.role === 'assistant')
              .map(m => ({ role: m.role, content: m.content })),
          }),
        });
        if (!resp.ok || !resp.body) {
          this.messages.push({ role: 'error', content: 'HTTP ' + resp.status });
          return;
        }
        await this._consumeSSE(resp.body);
      } catch (e) {
        this.messages.push({ role: 'error', content: 'fetch failed: ' + e });
      } finally {
        this.sending = false;
        this._scrollToBottom();
      }
    },

    async _consumeSSE(stream) {
      const reader = stream.getReader();
      const decoder = new TextDecoder();
      let buf = '';
      // accumulator for `event:` lines spanning the chunk boundary
      let currentEvent = null;
      let currentData = '';

      const flushEvent = () => {
        if (!currentEvent) {
          currentData = '';
          return;
        }
        let parsed;
        try { parsed = currentData ? JSON.parse(currentData) : {}; }
        catch (e) { parsed = { _raw: currentData }; }
        this._handleEvent(currentEvent, parsed);
        currentEvent = null;
        currentData = '';
      };

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        // SSE spec: events separated by a blank line; lines by \n.
        let idx;
        while ((idx = buf.indexOf('\n')) >= 0) {
          const line = buf.slice(0, idx);
          buf = buf.slice(idx + 1);
          if (line === '') {
            flushEvent();
          } else if (line.startsWith('event:')) {
            currentEvent = line.slice(6).trim();
          } else if (line.startsWith('data:')) {
            // SSE allows multi-line data; concatenate with newline.
            currentData += (currentData ? '\n' : '') + line.slice(5).trim();
          }
          // ignore other field lines (id:, retry:)
        }
      }
      flushEvent();
    },

    _handleEvent(event, data) {
      if (event === 'token') {
        // Real impl: append to the last assistant message; today unused.
        const last = this.messages[this.messages.length - 1];
        if (last && last.role === 'assistant') {
          last.content += data.text || '';
        } else {
          this.messages.push({ role: 'assistant', content: data.text || '' });
        }
        this._scrollToBottom();
      } else if (event === 'tool_use') {
        this.messages.push({
          role: 'assistant',
          content: '→ ' + (data.tool || '?') + '(' + JSON.stringify(data.input || {}) + ')',
        });
      } else if (event === 'tool_result') {
        this.messages.push({
          role: 'assistant',
          content: '✓ ' + (data.tool || '?') + ': ' + (data.summary || ''),
        });
      } else if (event === 'error') {
        this.messages.push({ role: 'error', content: data.message || 'unknown error' });
      } else if (event === 'done') {
        // No-op for now; real impl might surface usage / cost.
      }
    },

    /* ---------- voice ---------- */

    _initVoice() {
      const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
      if (!SR) { this.voiceSupported = false; return; }
      this.voiceSupported = true;
      this._recognition = new SR();
      this._recognition.continuous = false;
      this._recognition.interimResults = true;
      this._recognition.lang = 'en-US';
      this._recognition.onresult = (e) => {
        const t = Array.from(e.results).map(r => r[0].transcript).join('');
        this.voiceTranscript = t;
        this.input = t;
      };
      this._recognition.onerror = (e) => {
        this.voiceListening = false;
        this.messages.push({
          role: 'error',
          content: 'voice: ' + (e.error || 'unknown error'),
        });
      };
      this._recognition.onend = () => {
        this.voiceListening = false;
        const final = (this.voiceTranscript || '').trim();
        if (final) this.send(final);
      };
    },

    startVoice() {
      if (!this.voiceSupported || this.voiceListening || this.sending) return;
      this.voiceTranscript = '';
      try {
        this._recognition.start();
        this.voiceListening = true;
      } catch (e) {
        // start() throws if already started; ignore.
      }
    },

    stopVoice() {
      if (!this.voiceListening) return;
      try { this._recognition.stop(); } catch (e) { /* ignore */ }
    },

    _initSpaceShortcut() {
      // Hold Space (when chat textarea is NOT focused) to push-to-talk.
      // Skip when the user is typing in any input — only fires when the
      // body has focus, which is the default state in the admin.
      const isTyping = () => {
        const el = document.activeElement;
        if (!el) return false;
        const tag = el.tagName;
        return tag === 'INPUT' || tag === 'TEXTAREA' || el.isContentEditable;
      };
      document.addEventListener('keydown', (e) => {
        if (e.code !== 'Space' || e.repeat || isTyping() || !this.voiceSupported) return;
        e.preventDefault();
        this._spaceDown = true;
        this.startVoice();
      });
      document.addEventListener('keyup', (e) => {
        if (e.code !== 'Space' || !this._spaceDown) return;
        e.preventDefault();
        this._spaceDown = false;
        this.stopVoice();
      });
    },

    /* ---------- helpers ---------- */

    _scrollToBottom() {
      // After Alpine renders the new message, scroll the log to the bottom.
      this.$nextTick(() => {
        const log = this.$refs.log;
        if (log) log.scrollTop = log.scrollHeight;
      });
    },
  };
}

window.v2ChatView = v2ChatView;
document.addEventListener('alpine:init', () => {
  Alpine.data('v2ChatView', v2ChatView);
});
