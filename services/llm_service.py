"""Reasoning layer: configurable LLM provider + FAQ retrieval fallback.

WHAT IS CONNECTED
-----------------
* Any OpenAI-compatible "/chat/completions" server can be plugged in through
  LLM_BASE_URL / LLM_MODEL / LLM_API_KEY in .env.
* Gnani Evon (gnani-evon-v3.3) is published as open weights on Hugging Face and
  is served through vLLM / SGLang, which expose exactly that API. We found no
  public hosted Evon endpoint in the official docs, so none is hard-coded here.
  If you self-host Evon, point LLM_BASE_URL at your server.
* If no provider is configured (or it fails), the app falls back to retrieving
  an answer from the demonstration FAQ file. The reply is always labelled with
  its source ("llm", "faq" or "fallback") so nothing is passed off as live AI.
"""
import json
import logging
import re
from pathlib import Path

import requests

from config import LANGUAGES

log = logging.getLogger(__name__)

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_PUNCT = ".,;:!?()[]{}\"'`।॥-"
_STOPWORDS = {
    "the", "a", "an", "is", "are", "to", "of", "in", "on", "for", "and", "or", "how", "what",
    "do", "does", "i", "my", "me", "can", "where", "when", "which", "should", "about", "it",
    "you", "your", "please", "tell", "with", "be", "get", "find",
}


class FaqKnowledgeBase:
    """Loads faq_data.json (re-reads the file whenever you edit it)."""

    def __init__(self, path):
        self.path = Path(path)
        self._mtime = None
        self._data = {"_notice": "", "categories": [], "faqs": []}

    def _load(self):
        try:
            mtime = self.path.stat().st_mtime
            if mtime != self._mtime:
                self._data = json.loads(self.path.read_text(encoding="utf-8"))
                self._mtime = mtime
        except (OSError, ValueError) as exc:
            log.error("Could not load FAQ file %s: %s", self.path, exc)

    @property
    def notice(self):
        self._load()
        return self._data.get("_notice", "")

    @property
    def categories(self):
        self._load()
        return self._data.get("categories", [])

    @property
    def faqs(self):
        self._load()
        return self._data.get("faqs", [])

    @staticmethod
    def _tokens(text):
        words = [w.strip(_PUNCT) for w in (text or "").lower().split()]
        return {w for w in words if w and w not in _STOPWORDS}

    def _score(self, faq, query):
        q = (query or "").lower()
        qtokens = self._tokens(q)
        score = 0
        for kw in faq.get("keywords", []):
            kw_l = kw.lower()
            if kw_l.isascii():
                # whole-word prefix match so "exam" also matches "exams"
                if re.search(r"\b" + re.escape(kw_l) + r"\w*", q):
                    score += 3
            elif kw_l in q:  # Indian scripts: plain substring match
                score += 3
        text_tokens = self._tokens(faq.get("question", ""))
        score += len(qtokens & text_tokens)
        return score

    def search(self, query="", category=None, limit=None, min_score=1):
        """Return FAQs ranked by relevance. Empty query returns the category list."""
        items = [f for f in self.faqs if not category or f.get("category") == category]
        if not (query or "").strip():
            return items[:limit] if limit else items
        scored = [(self._score(f, query), f) for f in items]
        scored = [pair for pair in scored if pair[0] >= min_score]
        scored.sort(key=lambda pair: -pair[0])
        results = [f for _, f in scored]
        return results[:limit] if limit else results


class LLMService:
    def __init__(self, base_url, api_key, model, label, timeout, max_tokens,
                 disable_thinking, kb: FaqKnowledgeBase):
        self.base_url = (base_url or "").rstrip("/")
        self.api_key = api_key
        self.model = model
        self.label = label
        self.timeout = timeout
        self.max_tokens = max_tokens
        self.disable_thinking = disable_thinking
        self.kb = kb

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.model)

    @property
    def endpoint(self) -> str:
        if self.base_url.endswith("/chat/completions"):
            return self.base_url
        return self.base_url + "/chat/completions"

    # ------------------------------------------------------------------
    def reply(self, text, language, history=None, mode="assistant") -> dict:
        """Return {text, language, source, notice}."""
        notice = None
        matches = self.kb.search(text, limit=3, min_score=3)

        if self.configured:
            try:
                answer = self._call_llm(text, language, history or [], mode, matches)
                if answer:
                    return {"text": answer, "language": language, "source": "llm", "notice": None}
                notice = "The reasoning model returned an empty answer, so the FAQ fallback was used."
            except requests.Timeout:
                notice = "The reasoning model timed out, so the FAQ fallback was used."
            except (requests.RequestException, ValueError, KeyError) as exc:
                log.warning("LLM call failed: %s", type(exc).__name__)
                notice = "The reasoning model is unavailable, so the FAQ fallback was used."
        else:
            notice = ("No reasoning model is configured (see LLM_* in .env), "
                      "so answers come from the demo FAQ only.")

        return self._faq_reply(matches, notice)

    # ------------------------------------------------------------------
    def _faq_reply(self, matches, notice):
        if matches:
            return {"text": matches[0]["answer"], "language": "en-IN", "source": "faq",
                    "notice": notice}
        return {
            "text": ("I could not find that in the demonstration knowledge base, and no reasoning "
                     "model is available right now. Try asking about courses, exams, attendance, "
                     "the library, hostel, scholarships or study tips."),
            "language": "en-IN", "source": "fallback", "notice": notice,
        }

    def _system_prompt(self, language, mode, matches):
        lang_name = LANGUAGES.get(language, LANGUAGES["en-IN"])["name"]
        prompt = (
            "You are BhashaBridge AI, a friendly multilingual voice assistant for Indian students. "
            f"Reply in {lang_name} (language code {language}) unless the user clearly writes in another language. "
            "Your reply will be read aloud: use plain sentences, no markdown, no bullet lists, no emojis, "
            "and keep it under about 80 words. "
            "Never invent college, university, fee, date or policy facts. If asked for such details, say you "
            "do not have verified information and suggest checking the official college source or office. "
            "For study help, explain simply and give short practical steps."
        )
        if mode == "student":
            prompt += " Focus on student help: courses, exams, campus questions, study guidance and career guidance."
        if matches:
            context = "\n".join(f"- Q: {m['question']} A: {m['answer']}" for m in matches)
            prompt += ("\n\n<demo_knowledge>\nThis is DEMONSTRATION content, not verified college policy. "
                       "If you use it, say it is demo information.\n" + context + "\n</demo_knowledge>")
        return prompt

    def _call_llm(self, text, language, history, mode, matches):
        messages = [{"role": "system", "content": self._system_prompt(language, mode, matches)}]
        for m in history[-8:]:
            if m.get("role") in ("user", "assistant") and m.get("content"):
                messages.append({"role": m["role"], "content": m["content"]})
        messages.append({"role": "user", "content": text})

        payload = {"model": self.model, "messages": messages, "max_tokens": self.max_tokens,
                   "temperature": 0.5}
        if self.disable_thinking:
            payload["chat_template_kwargs"] = {"enable_thinking": False}
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        resp = requests.post(self.endpoint, json=payload, headers=headers, timeout=self.timeout)
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"] or ""
        return self._clean(content)

    @staticmethod
    def _clean(content: str) -> str:
        content = _THINK_RE.sub("", content)
        if "</think>" in content:  # model emitted only the closing tag
            content = content.split("</think>")[-1]
        content = re.sub(r"[*_`#]+", "", content)
        return re.sub(r"\s+", " ", content).strip()
