/* BhashaBridge AI - chat widget (used on the Assistant and Student pages). */
(function () {
  "use strict";

  const SUGGESTIONS = {
    assistant: [
      "How should I prepare for my exams?",
      "Give me a simple study plan",
      "How do I stay focused while studying?",
    ],
    student: [
      "What do I need on exam day?",
      "How do I find scholarships?",
      "How do I choose an elective?",
    ],
  };

  const SOURCE_LABEL = {
    llm: "AI answer",
    faq: "Demo FAQ answer",
    fallback: "Fallback message",
  };

  class Chat {
    constructor(root) {
      this.root = root;
      this.mode = root.dataset.mode || "assistant";
      this.$ = (sel) => root.querySelector(sel);
      this.messagesEl = this.$("[data-messages]");
      this.emptyEl = this.$("[data-empty]");
      this.input = this.$("[data-input]");
      this.langSel = this.$("[data-language]");
      this.micBtn = this.$("[data-mic]");
      this.banner = this.$("[data-rec-banner]");
      this.autoplay = this.$("[data-autoplay]");
      this.busy = false;
      this.audioCache = new Map();   // message element -> blob URL
      this.currentAudio = null;
      this.recorder = null;
      this.languages = [];

      this.$("[data-form]").addEventListener("submit", (e) => { e.preventDefault(); this.sendText(); });
      this.$("[data-clear]").addEventListener("click", () => this.clear());
      this.micBtn.addEventListener("click", () => this.toggleMic());
      this.langSel.addEventListener("change", () => BB.setPref("bb_lang", this.langSel.value));
      this.autoplay.checked = BB.getPref("bb_autoplay") !== "0";
      this.autoplay.addEventListener("change", () => BB.setPref("bb_autoplay", this.autoplay.checked ? "1" : "0"));

      this.renderSuggestions();
      this.init();
    }

    async init() {
      try {
        const cfg = await BB.api("/api/config");
        this.languages = cfg.languages;
        this.maxSeconds = cfg.max_record_seconds;
        const saved = BB.getPref("bb_lang");
        this.langSel.innerHTML = "";
        cfg.languages.forEach((l) => {
          const o = document.createElement("option");
          o.value = l.code;
          o.textContent = l.native === l.name ? l.name : l.name + " · " + l.native;
          this.langSel.appendChild(o);
        });
        if (saved && cfg.languages.some((l) => l.code === saved)) this.langSel.value = saved;
      } catch (e) { BB.toast(e.message, "error"); }

      if (!VoiceRecorder.supported()) {
        this.micBtn.disabled = true;
        this.micBtn.title = "Recording is not supported in this browser. You can still type.";
      }

      try {
        const h = await BB.api("/api/history");
        h.messages.forEach((m) => this.addMessage(m.role, m.content, { language: m.language, source: m.source, at: m.created_at }, false));
      } catch (e) { /* history is optional */ }
      this.updateEngine();
    }

    async updateEngine() {
      const data = await BB.refreshHealth();
      if (!data) return;
      const r = data.services.reasoning;
      const label = r.configured ? r.label : "Demo FAQ fallback (no reasoning model configured)";
      const sub = this.$("[data-engine]");
      if (sub) sub.textContent = "Reasoning: " + label;
      const side = document.querySelector("[data-side-engine]");
      if (side) side.textContent = label;
    }

    renderSuggestions() {
      const box = this.$("[data-suggestions]");
      (SUGGESTIONS[this.mode] || SUGGESTIONS.assistant).forEach((s) => {
        const b = document.createElement("button");
        b.type = "button"; b.className = "chip"; b.textContent = s;
        b.addEventListener("click", () => { this.input.value = s; this.sendText(); });
        box.appendChild(b);
      });
    }

    setBusy(b) {
      this.busy = b;
      this.root.classList.toggle("busy", b);
      this.$("[data-send]").disabled = b;
      this.input.disabled = b;
    }

    scrollDown() { this.messagesEl.scrollTop = this.messagesEl.scrollHeight; }

    // ---------- messages ----------
    addMessage(role, text, meta = {}, scroll = true) {
      if (this.emptyEl) { this.emptyEl.hidden = true; }
      const wrap = document.createElement("div");
      wrap.className = "msg " + role;
      const bubble = document.createElement("div");
      bubble.className = "bubble-msg";
      const p = document.createElement("p");
      p.textContent = text;            // textContent: never interpret model output as HTML
      bubble.appendChild(p);

      const foot = document.createElement("div");
      foot.className = "msg-foot";
      const time = document.createElement("time");
      time.textContent = BB.formatTime(meta.at);
      foot.appendChild(time);

      if (role === "assistant") {
        if (meta.source && SOURCE_LABEL[meta.source]) {
          const tag = document.createElement("span");
          tag.className = "tag tag-" + meta.source;
          tag.textContent = SOURCE_LABEL[meta.source];
          foot.appendChild(tag);
        }
        const lang = meta.language || this.langSel.value;
        const play = this.iconBtn("Play", "▶", () => this.play(wrap, text, lang, play));
        const copy = this.iconBtn("Copy", "⧉", () => this.copy(text, copy));
        foot.appendChild(play);
        foot.appendChild(copy);
        wrap._play = play;
        wrap._lang = lang;
      }
      bubble.appendChild(foot);
      wrap.appendChild(bubble);
      this.messagesEl.appendChild(wrap);
      if (scroll) this.scrollDown();
      return wrap;
    }

    iconBtn(label, glyph, onClick) {
      const b = document.createElement("button");
      b.type = "button"; b.className = "mini";
      b.setAttribute("aria-label", label);
      const g = document.createElement("span"); g.textContent = glyph; g.setAttribute("aria-hidden", "true");
      const t = document.createElement("span"); t.textContent = label; t.className = "mini-t";
      b.append(g, t);
      b.addEventListener("click", onClick);
      return b;
    }

    addTyping() {
      if (this.emptyEl) this.emptyEl.hidden = true;
      const el = document.createElement("div");
      el.className = "msg assistant typing";
      el.innerHTML = '<div class="bubble-msg"><span class="dots"><i></i><i></i><i></i></span></div>';
      this.messagesEl.appendChild(el);
      this.scrollDown();
      return el;
    }

    async copy(text, btn) {
      try {
        await navigator.clipboard.writeText(text);
        const t = btn.querySelector(".mini-t"); const old = t.textContent;
        t.textContent = "Copied"; setTimeout(() => (t.textContent = old), 1500);
      } catch (e) { BB.toast("Could not copy. Select the text and copy manually.", "error"); }
    }

    // ---------- audio playback (Timbre) ----------
    async play(msgEl, text, lang, btn) {
      if (this.currentAudio) { this.currentAudio.pause(); this.currentAudio = null; }
      const label = btn ? btn.querySelector(".mini-t") : null;
      try {
        let url = this.audioCache.get(msgEl);
        if (!url) {
          if (label) label.textContent = "Loading…";
          if (btn) btn.disabled = true;
          const res = await BB.api("/api/voice/speak", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text, language: lang }),
          });
          url = URL.createObjectURL(await res.blob());
          this.audioCache.set(msgEl, url);     // replay without calling Timbre again
          BB.refreshHealth();
        }
        const audio = new Audio(url);
        this.currentAudio = audio;
        if (label) label.textContent = "Playing…";
        audio.onended = audio.onpause = () => { if (label) label.textContent = this.audioCache.has(msgEl) ? "Replay" : "Play"; };
        await audio.play();
      } catch (e) {
        BB.toast(e.name === "NotAllowedError" ? "Your browser blocked autoplay. Press Play." : e.message, "error");
        if (label) label.textContent = "Play";
      } finally {
        if (btn) btn.disabled = false;
      }
    }

    // ---------- sending ----------
    async sendText() {
      const text = this.input.value.trim();
      if (!text || this.busy) return;
      this.input.value = "";
      await this.ask(text);
    }

    async ask(text) {
      this.setBusy(true);
      this.addMessage("user", text);
      const typing = this.addTyping();
      try {
        const lang = this.langSel.value;
        const data = await BB.api("/api/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message: text, language: lang, mode: this.mode }),
        });
        typing.remove();
        const msg = this.addMessage("assistant", data.reply, { language: data.language, source: data.source, at: data.created_at });
        if (data.notice) BB.toast(data.notice, "warn", 7000);
        this.updateEngine();
        if (this.autoplay.checked) this.play(msg, data.reply, data.language, msg._play);
      } catch (e) {
        typing.remove();
        BB.toast(e.message, "error");
      } finally {
        this.setBusy(false);
        this.input.focus({ preventScroll: true });
      }
    }

    async clear() {
      if (!confirm("Delete this conversation?")) return;
      try {
        await BB.api("/api/history", { method: "DELETE" });
        this.messagesEl.querySelectorAll(".msg").forEach((n) => n.remove());
        this.audioCache.forEach((u) => URL.revokeObjectURL(u));
        this.audioCache.clear();
        if (this.currentAudio) this.currentAudio.pause();
        this.emptyEl.hidden = false;
        BB.toast("Conversation cleared.", "info", 2500);
      } catch (e) { BB.toast(e.message, "error"); }
    }

    // ---------- microphone (Prisma) ----------
    async toggleMic() {
      if (this.busy && !(this.recorder && this.recorder.recording)) return;
      if (this.recorder && this.recorder.recording) return this.finishRecording();
      this.recorder = new VoiceRecorder({
        maxSeconds: this.maxSeconds || 28,
        onTick: (s) => {
          const m = Math.floor(s / 60), sec = String(Math.floor(s % 60)).padStart(2, "0");
          this.$("[data-rec-time]").textContent = m + ":" + sec;
        },
        onLevel: (v) => this.micBtn.style.setProperty("--level", v.toFixed(2)),
        onAutoStop: () => this.finishRecording(),
      });
      try {
        if (this.currentAudio) this.currentAudio.pause();
        await this.recorder.start();
      } catch (e) { BB.toast(e.message, "error", 8000); this.recorder = null; return; }
      this.micBtn.classList.add("recording");
      this.micBtn.setAttribute("aria-pressed", "true");
      this.micBtn.setAttribute("aria-label", "Stop recording");
      this.banner.hidden = false;
      this.$("[data-rec-text]").textContent = "Listening… tap to stop";
    }

    resetMic() {
      this.micBtn.classList.remove("recording", "processing");
      this.micBtn.setAttribute("aria-pressed", "false");
      this.micBtn.setAttribute("aria-label", "Start recording");
      this.micBtn.style.removeProperty("--level");
      this.banner.hidden = true;
    }

    async finishRecording() {
      if (!this.recorder || !this.recorder.recording) return;
      this.micBtn.classList.remove("recording");
      this.micBtn.classList.add("processing");
      this.banner.hidden = false;
      this.$("[data-rec-text]").textContent = "Processing your voice…";
      this.setBusy(true);
      try {
        const { blob } = await this.recorder.stop();
        const form = new FormData();
        form.append("audio", blob, "recording.wav");
        form.append("language", this.langSel.value);
        const data = await BB.api("/api/voice/transcribe", { method: "POST", body: form });
        BB.refreshHealth();
        this.resetMic();
        this.setBusy(false);
        await this.ask(data.transcript);          // shows the transcription as the user message
      } catch (e) {
        this.resetMic();
        this.setBusy(false);
        BB.toast(e.message, "error", 8000);
      } finally {
        this.recorder = null;
      }
    }
  }

  document.querySelectorAll("[data-chat]").forEach((el) => { window.bbChat = new Chat(el); });
})();
