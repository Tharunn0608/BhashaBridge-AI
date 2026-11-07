/* BhashaBridge AI - student FAQ browser (search + categories). */
(function () {
  "use strict";
  const list = document.querySelector("[data-faq-list]");
  const catsEl = document.querySelector("[data-cats]");
  const qEl = document.querySelector("[data-faq-q]");
  const form = document.querySelector("[data-faq-search]");
  const noticeEl = document.querySelector("[data-notice-text]");
  let category = "";
  let timer = null;

  function renderCats(cats) {
    if (catsEl.childElementCount) return;
    [{ id: "", name: "All" }].concat(cats).forEach((c) => {
      const b = document.createElement("button");
      b.type = "button"; b.className = "chip" + (c.id === category ? " on" : "");
      b.textContent = c.name; b.dataset.id = c.id;
      b.setAttribute("role", "tab");
      b.addEventListener("click", () => {
        category = c.id;
        catsEl.querySelectorAll(".chip").forEach((x) => x.classList.toggle("on", x === b));
        load();
      });
      catsEl.appendChild(b);
    });
  }

  function render(faqs) {
    list.innerHTML = "";
    if (!faqs.length) {
      const p = document.createElement("p");
      p.className = "muted empty-faq";
      p.textContent = "No matching questions. Try other words, or ask the assistant on the right.";
      list.appendChild(p);
      return;
    }
    faqs.forEach((f) => {
      const d = document.createElement("details");
      d.className = "card faq";
      const s = document.createElement("summary"); s.textContent = f.question;
      const a = document.createElement("p"); a.textContent = f.answer;
      const ask = document.createElement("button");
      ask.type = "button"; ask.className = "btn btn-ghost btn-sm"; ask.textContent = "Ask the assistant about this";
      ask.addEventListener("click", () => {
        if (window.bbChat) { window.bbChat.input.value = f.question; window.bbChat.sendText(); }
      });
      d.append(s, a, ask);
      list.appendChild(d);
    });
  }

  async function load() {
    const params = new URLSearchParams();
    if (qEl.value.trim()) params.set("q", qEl.value.trim());
    if (category) params.set("category", category);
    try {
      const data = await BB.api("/api/faq?" + params.toString());
      noticeEl.textContent = (data.notice || "These entries are examples only.");
      renderCats(data.categories);
      render(data.faqs);
    } catch (e) { BB.toast(e.message, "error"); }
  }

  form.addEventListener("submit", (e) => { e.preventDefault(); load(); });
  qEl.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(load, 250); });
  load();
})();
