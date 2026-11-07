"""Health / configuration endpoints (never expose secrets)."""
from flask import Blueprint

from config import LANGUAGES

from .helpers import services

bp = Blueprint("health", __name__, url_prefix="/api")


@bp.get("/health")
def health():
    bb = services()
    cfg = bb["config"]
    status = bb["status"].last
    return {
        "ok": True,
        "app": cfg.APP_NAME,
        "version": cfg.APP_VERSION,
        "services": {
            # "configured" only means a key/endpoint is set. "last_call" is the outcome of the
            # most recent real request, so the badge never claims a service works untested.
            "prisma": {"configured": bb["prisma"].configured, "model": cfg.STT_MODEL,
                       "last_call": status["prisma"]},
            "timbre": {"configured": bb["timbre"].configured, "model": cfg.TTS_MODEL,
                       "last_call": status["timbre"]},
            "reasoning": {"configured": bb["llm"].configured,
                          "label": cfg.LLM_LABEL if bb["llm"].configured else "FAQ fallback only",
                          "last_call": status["llm"]},
        },
    }


@bp.get("/config")
def public_config():
    cfg = services()["config"]
    return {
        "ok": True,
        "languages": [{"code": c, **meta} for c, meta in LANGUAGES.items()],
        "max_record_seconds": cfg.MAX_AUDIO_SECONDS - 2,
    }
