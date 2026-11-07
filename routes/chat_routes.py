"""Chat, history and FAQ endpoints."""
from flask import Blueprint, request

from .helpers import get_session_id, json_error, services, valid_language

bp = Blueprint("chat", __name__, url_prefix="/api")

MAX_MESSAGE_CHARS = 1000


@bp.post("/chat")
def chat():
    bb = services()
    body = request.get_json(silent=True) or {}
    text = (body.get("message") or "").strip()
    if not text:
        return json_error("Please type or say something first.", 400, "EMPTY_MESSAGE")
    if len(text) > MAX_MESSAGE_CHARS:
        return json_error(f"Message is too long (max {MAX_MESSAGE_CHARS} characters).", 400, "TOO_LONG")

    language = valid_language(body.get("language"))
    mode = "student" if body.get("mode") == "student" else "assistant"
    sid = get_session_id()
    convo = bb["conversations"]

    history = convo.history(sid, limit=8)  # context for follow-up questions
    convo.add(sid, "user", text, language)
    result = bb["llm"].reply(text, language, history=history, mode=mode)
    if result["source"] == "llm":
        bb["status"].record_ok("llm")
    # FAQ answers are written in English, so tell the browser which voice language to use.
    created = convo.add(sid, "assistant", result["text"], result["language"], result["source"])

    return {"ok": True, "reply": result["text"], "language": result["language"],
            "source": result["source"], "notice": result["notice"], "created_at": created}


@bp.get("/history")
def history():
    return {"ok": True, "messages": services()["conversations"].history(get_session_id())}


@bp.delete("/history")
def clear_history():
    removed = services()["conversations"].clear(get_session_id())
    return {"ok": True, "removed": removed}


@bp.get("/faq")
def faq():
    kb = services()["kb"]
    q = request.args.get("q", "").strip()[:200]
    category = request.args.get("category", "").strip() or None
    items = kb.search(q, category=category, min_score=1)
    return {"ok": True, "notice": kb.notice, "categories": kb.categories,
            "faqs": [{k: f[k] for k in ("id", "category", "question", "answer")} for f in items]}
