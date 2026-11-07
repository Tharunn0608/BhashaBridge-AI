"""Small shared helpers for the route modules."""
import re

from flask import current_app, jsonify, request

from config import LANGUAGES
from services.gnani_common import GnaniError

_SESSION_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


def json_error(message, status=400, code="BAD_REQUEST"):
    return jsonify({"ok": False, "error": {"code": code, "message": message}}), status


def gnani_error_response(exc: GnaniError):
    current_app.extensions["bb"]["status"].record_failure(exc)
    return json_error(exc.message, exc.http_status, exc.code)


def get_session_id():
    """Session ids are random strings made by the browser (never user identities)."""
    sid = request.headers.get("X-Session-Id", "")
    return sid if _SESSION_RE.match(sid) else "anonymous"


def valid_language(code, default="en-IN"):
    return code if code in LANGUAGES else default


def services():
    return current_app.extensions["bb"]


class ApiStatus:
    """Remembers the outcome of the last real call to each service (for the health badge)."""

    def __init__(self):
        self.last = {"prisma": None, "timbre": None, "llm": None}

    def record_ok(self, name):
        self.last[name] = {"ok": True}

    def record_failure(self, exc):
        # exc.code is e.g. INVALID_API_KEY; the message is user-safe
        name = "timbre" if "Timbre" in exc.message else "prisma" if "Prisma" in exc.message else None
        if name:
            self.last[name] = {"ok": False, "code": exc.code, "message": exc.message}
