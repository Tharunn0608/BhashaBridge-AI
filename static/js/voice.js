/* BhashaBridge AI - microphone recording.
 *
 * Browsers record in different formats (Chrome: WebM, Firefox: OGG, Safari: MP4) and Gnani
 * Prisma does NOT list WebM among its supported formats. So after recording we decode the clip
 * with the Web Audio API and re-encode it as 16 kHz mono 16-bit WAV, which Prisma supports.
 * Everything happens in memory in the browser.
 */
(function () {
  "use strict";

  const TARGET_RATE = 16000;

  function pickMime() {
    const options = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/mp4"];
    if (!window.MediaRecorder) return "";
    return options.find((m) => MediaRecorder.isTypeSupported(m)) || "";
  }

  function writeStr(view, offset, s) {
    for (let i = 0; i < s.length; i++) view.setUint8(offset + i, s.charCodeAt(i));
  }

  /** Float32 samples -> 16-bit PCM WAV Blob. */
  function encodeWav(samples, rate) {
    const buffer = new ArrayBuffer(44 + samples.length * 2);
    const view = new DataView(buffer);
    writeStr(view, 0, "RIFF");
    view.setUint32(4, 36 + samples.length * 2, true);
    writeStr(view, 8, "WAVE");
    writeStr(view, 12, "fmt ");
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true);            // PCM
    view.setUint16(22, 1, true);            // mono
    view.setUint32(24, rate, true);
    view.setUint32(28, rate * 2, true);     // byte rate
    view.setUint16(32, 2, true);            // block align
    view.setUint16(34, 16, true);           // bits per sample
    writeStr(view, 36, "data");
    view.setUint32(40, samples.length * 2, true);
    let offset = 44;
    for (let i = 0; i < samples.length; i++, offset += 2) {
      const s = Math.max(-1, Math.min(1, samples[i]));
      view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true);
    }
    return new Blob([buffer], { type: "audio/wav" });
  }

  /** Decode any browser-recorded blob and return a 16 kHz mono WAV blob. */
  async function toWav(blob) {
    const AC = window.AudioContext || window.webkitAudioContext;
    const ctx = new AC();
    try {
      const arr = await blob.arrayBuffer();
      const decoded = await new Promise((resolve, reject) => {
        // callback form works on older Safari too
        ctx.decodeAudioData(arr, resolve, reject);
      });
      const frames = Math.max(1, Math.ceil(decoded.duration * TARGET_RATE));
      const Offline = window.OfflineAudioContext || window.webkitOfflineAudioContext;
      const off = new Offline(1, frames, TARGET_RATE);   // 1 channel => automatic downmix
      const src = off.createBufferSource();
      src.buffer = decoded;
      src.connect(off.destination);
      src.start();
      const rendered = await new Promise((resolve, reject) => {
        const p = off.startRendering();
        if (p && p.then) p.then(resolve, reject); else off.oncomplete = (e) => resolve(e.renderedBuffer);
      });
      return { blob: encodeWav(rendered.getChannelData(0), TARGET_RATE), seconds: decoded.duration };
    } finally {
      if (ctx.close) ctx.close();
    }
  }

  class VoiceRecorder {
    /**
     * @param {object} opts  maxSeconds, onTick(seconds), onLevel(0..1), onAutoStop()
     */
    constructor(opts = {}) {
      this.maxSeconds = opts.maxSeconds || 28;
      this.onTick = opts.onTick || (() => {});
      this.onLevel = opts.onLevel || (() => {});
      this.onAutoStop = opts.onAutoStop || (() => {});
      this.recording = false;
    }

    static supported() {
      return !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia && window.MediaRecorder);
    }

    async start() {
      if (!VoiceRecorder.supported()) {
        throw new Error("This browser cannot record audio. Please use a recent Chrome, Edge, Firefox or Safari.");
      }
      if (!window.isSecureContext) {
        throw new Error("Microphone access needs https or http://localhost. Open the app at http://127.0.0.1:5000.");
      }
      try {
        this.stream = await navigator.mediaDevices.getUserMedia({
          audio: { echoCancellation: true, noiseSuppression: true, channelCount: 1 },
        });
      } catch (e) {
        if (e && (e.name === "NotAllowedError" || e.name === "SecurityError")) {
          throw new Error("Microphone permission was denied. Allow it in your browser's address bar and try again.");
        }
        if (e && (e.name === "NotFoundError" || e.name === "OverconstrainedError")) {
          throw new Error("No microphone was found. Connect one and try again.");
        }
        throw new Error("Could not start the microphone: " + (e && e.message ? e.message : "unknown error"));
      }

      this.chunks = [];
      this.mime = pickMime();
      this.recorder = new MediaRecorder(this.stream, this.mime ? { mimeType: this.mime } : undefined);
      this.recorder.ondataavailable = (e) => { if (e.data && e.data.size) this.chunks.push(e.data); };
      this.recorder.start(250);
      this.recording = true;
      this.startedAt = Date.now();
      this._startMeter();

      this.timer = setInterval(() => {
        const secs = (Date.now() - this.startedAt) / 1000;
        this.onTick(secs);
        if (secs >= this.maxSeconds) this.onAutoStop();
      }, 200);
    }

    _startMeter() {
      try {
        const AC = window.AudioContext || window.webkitAudioContext;
        this.meterCtx = new AC();
        const source = this.meterCtx.createMediaStreamSource(this.stream);
        const analyser = this.meterCtx.createAnalyser();
        analyser.fftSize = 256;
        source.connect(analyser);
        const data = new Uint8Array(analyser.frequencyBinCount);
        const loop = () => {
          if (!this.recording) return;
          analyser.getByteTimeDomainData(data);
          let peak = 0;
          for (let i = 0; i < data.length; i++) peak = Math.max(peak, Math.abs(data[i] - 128));
          this.onLevel(Math.min(1, peak / 64));
          this.raf = requestAnimationFrame(loop);
        };
        loop();
      } catch (e) { /* the level meter is optional */ }
    }

    /** Stop and resolve to {blob, seconds} (WAV when conversion works). */
    stop() {
      return new Promise((resolve, reject) => {
        if (!this.recording) return reject(new Error("Not recording."));
        this.recording = false;
        clearInterval(this.timer);
        cancelAnimationFrame(this.raf);
        const seconds = (Date.now() - this.startedAt) / 1000;
        this.recorder.onstop = async () => {
          this.stream.getTracks().forEach((t) => t.stop());   // release the microphone
          if (this.meterCtx && this.meterCtx.close) this.meterCtx.close();
          const raw = new Blob(this.chunks, { type: this.recorder.mimeType || this.mime || "audio/webm" });
          this.chunks = [];
          if (seconds < 0.4 || raw.size < 500) return reject(new Error("The recording was too short. Hold on a little longer."));
          try {
            resolve(await toWav(raw));
          } catch (e) {
            // Fall back to the raw clip only for formats Prisma accepts (OGG / MP4 = M4A).
            const t = raw.type.split(";")[0];
            if (t === "audio/ogg" || t === "audio/mp4") resolve({ blob: raw, seconds });
            else reject(new Error("This browser's recording format could not be converted. Try Chrome, Edge or Firefox."));
          }
        };
        this.recorder.stop();
      });
    }

    cancel() {
      if (!this.recording) return;
      this.recording = false;
      clearInterval(this.timer);
      cancelAnimationFrame(this.raf);
      this.recorder.onstop = () => {};
      try { this.recorder.stop(); } catch (e) { /* ignore */ }
      this.stream.getTracks().forEach((t) => t.stop());
      if (this.meterCtx && this.meterCtx.close) this.meterCtx.close();
    }
  }

  window.VoiceRecorder = VoiceRecorder;
  window.BBAudio = { toWav, encodeWav };
})();
