/* BhashaBridge AI - shared helpers: session id, API wrapper, toasts, nav, health badge. */
(function () {
  "use strict";

  // Random per-browser id used to keep this browser's chat history separate (not a user identity).
  function makeId() {
    const a = new Uint8Array(16);
    crypto.getRandomValues(a);
    return Array.from(a, (b) => b.toString(16).padStart(2, "0")).join("");
  }
  function safeGet(key) { try { return localStorage.getItem(key); } catch (e) { return null; } }
  function safeSet(key, val) { try { localStorage.setItem(key, val); } catch (e) { /* private mode */ } }

  let sid = safeGet("bb_session");
  if (!sid) { sid = makeId(); safeSet("bb_session", sid); }

  const BB = (window.BB = {
    sessionId: sid,
    getPref: safeGet,
    setPref: safeSet,

    /** fetch wrapper: returns parsed JSON or throws Error with a friendly message. */
    async api(path, options = {}) {
      const headers = Object.assign({ "X-Session-Id": sid }, options.headers || {});
      let res;
      try {
        res = await fetch(path, Object.assign({}, options, { headers }));
      } catch (e) {
        throw new Error("Cannot reach the BhashaBridge server. Is it still running?");
      }
      const type = res.headers.get("Content-Type") || "";
      if (type.includes("application/json")) {
        const data = await res.json();
        if (!res.ok || data.ok === false) {
          const msg = (data.error && data.error.message) || "Something went wrong.";
          const err = new Error(msg);
          err.code = data.error && data.error.code;
          throw err;
        }
        return data;
      }
      if (!res.ok) throw new Error("Request failed (" + res.status + ").");
      return res; // binary (audio)
    },

    toast(message, kind = "info", ms = 5000) {
      const box = document.querySelector("[data-toasts]");
      if (!box) return;
      const el = document.createElement("div");
      el.className = "toast " + kind;
      el.setAttribute("role", kind === "error" ? "alert" : "status");
      el.textContent = message;
      box.appendChild(el);
      setTimeout(() => { el.classList.add("out"); setTimeout(() => el.remove(), 300); }, ms);
    },

    formatTime(iso) {
      const d = iso ? new Date(iso) : new Date();
      return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    },
  });

  // ---- mobile nav ----
  const toggle = document.querySelector("[data-nav-toggle]");
  const nav = document.querySelector("[data-nav]");
  if (toggle && nav) {
    toggle.addEventListener("click", () => {
      const open = nav.classList.toggle("open");
      toggle.setAttribute("aria-expanded", String(open));
    });
  }

  // ---- health badge ----
  const pill = document.querySelector("[data-health-pill]");
  const pop = document.querySelector("[data-health-pop]");
  const dot = document.querySelector("[data-health-dot]");
  const text = document.querySelector("[data-health-text]");
  const list = document.querySelector("[data-health-list]");

  function stateOf(svc) {
    if (!svc.configured) return { cls: "bad", label: "Not configured" };
    if (svc.last_call && svc.last_call.ok === false) return { cls: "bad", label: "Last call failed" };
    if (svc.last_call && svc.last_call.ok) return { cls: "ok", label: "Working" };
    return { cls: "warn", label: "Ready (not yet tested)" };
  }

  async function refreshHealth() {
    if (!pill) return null;
    try {
      const res = await fetch("/api/health");
      const data = await res.json();
      const s = data.services;
      const rows = [
        ["Prisma · speech to text", stateOf(s.prisma)],
        ["Timbre · text to speech", stateOf(s.timbre)],
        ["Reasoning · " + s.reasoning.label, s.reasoning.configured ? stateOf(s.reasoning) : { cls: "warn", label: "FAQ fallback" }],
      ];
      list.innerHTML = "";
      rows.forEach(([name, st]) => {
        const li = document.createElement("li");
        li.innerHTML = '<span class="dot dot-' + st.cls + '"></span>';
        const span = document.createElement("span");
        span.textContent = name + ": " + st.label;
        li.appendChild(span);
        list.appendChild(li);
      });
      const bad = rows.some(([, st]) => st.cls === "bad" && !String(st.label).includes("FAQ"));
      const gnaniMissing = !s.prisma.configured || !s.timbre.configured;
      if (gnaniMissing) { dot.className = "dot dot-bad"; text.textContent = "Add API key"; }
      else if (bad) { dot.className = "dot dot-bad"; text.textContent = "Issue detected"; }
      else if (s.prisma.last_call && s.timbre.last_call) { dot.className = "dot dot-ok"; text.textContent = "All working"; }
      else { dot.className = "dot dot-warn"; text.textContent = "Ready"; }
      return data;
    } catch (e) {
      dot.className = "dot dot-bad"; text.textContent = "Server offline";
      return null;
    }
  }
  BB.refreshHealth = refreshHealth;

  if (pill) {
    pill.addEventListener("click", () => {
      const open = pop.hidden;
      pop.hidden = !open;
      pill.setAttribute("aria-expanded", String(open));
    });
    document.addEventListener("click", (e) => {
      if (!pop.hidden && !pop.contains(e.target) && !pill.contains(e.target)) {
        pop.hidden = true; pill.setAttribute("aria-expanded", "false");
      }
    });
    refreshHealth();
    setInterval(refreshHealth, 30000);
  }
})();
