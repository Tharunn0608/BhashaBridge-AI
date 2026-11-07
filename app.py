"""BhashaBridge AI - Flask application entry point.

Run with:  python app.py   (or use run.bat / run.sh)
"""
import logging

from flask import Flask, jsonify, render_template

from config import Config
from database.db import init_db
from routes import chat_routes, health_routes, voice_routes
from routes.helpers import ApiStatus
from services.conversation_service import ConversationService
from services.llm_service import FaqKnowledgeBase, LLMService
from services.prisma_service import PrismaService
from services.timbre_service import TimbreService


def create_app(config_class=Config, overrides=None):
    app = Flask(__name__)
    app.config.from_object(config_class)
    if overrides:
        app.config.update(overrides)
    cfg = config_class

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    db_path = app.config.get("DATABASE_PATH", cfg.DATABASE_PATH)
    init_db(db_path)

    kb = FaqKnowledgeBase(cfg.FAQ_PATH)
    # All services live in one dictionary so tests can swap them for mocks.
    app.extensions["bb"] = {
        "config": cfg,
        "status": ApiStatus(),
        "kb": kb,
        "conversations": ConversationService(db_path),
        "prisma": PrismaService(cfg.GNANI_API_KEY, cfg.GNANI_BASE_URL, cfg.STT_MODEL,
                                cfg.STT_FORMAT, cfg.GNANI_TIMEOUT, cfg.GNANI_RETRIES),
        "timbre": TimbreService(cfg.GNANI_API_KEY, cfg.GNANI_BASE_URL, cfg.TTS_MODEL, cfg.TTS_SPEED,
                                cfg.TTS_SAMPLE_RATE, cfg.TTS_MAX_CHARS, cfg.GNANI_TIMEOUT,
                                cfg.GNANI_RETRIES),
        "llm": LLMService(cfg.LLM_BASE_URL, cfg.LLM_API_KEY, cfg.LLM_MODEL, cfg.LLM_LABEL,
                          cfg.LLM_TIMEOUT, cfg.LLM_MAX_TOKENS, cfg.LLM_DISABLE_THINKING, kb),
    }

    # The frontend is served by this same app, so no CORS is needed.
    for bp in (voice_routes.bp, chat_routes.bp, health_routes.bp):
        app.register_blueprint(bp)

    @app.get("/")
    def index():
        return render_template("index.html", page="home")

    @app.get("/dashboard")
    def dashboard():
        return render_template("dashboard.html", page="dashboard")

    @app.get("/student")
    def student():
        return render_template("student_assistant.html", page="student")

    @app.get("/about")
    def about():
        return render_template("about.html", page="about")

    @app.errorhandler(413)
    def too_large(_):
        return jsonify(ok=False, error={"code": "AUDIO_TOO_LARGE",
                                        "message": "That upload is too large."}), 413

    @app.errorhandler(404)
    def not_found(_):
        return jsonify(ok=False, error={"code": "NOT_FOUND", "message": "Not found."}), 404

    @app.errorhandler(500)
    def server_error(_):
        return jsonify(ok=False, error={"code": "SERVER_ERROR",
                                        "message": "Something went wrong on the server."}), 500

    @app.after_request
    def security_headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "no-referrer")
        # Microphone is allowed for this site only.
        resp.headers.setdefault("Permissions-Policy", "microphone=(self)")
        return resp

    return app


if __name__ == "__main__":
    application = create_app()
    if not Config.GNANI_API_KEY:
        print("\n  NOTE: GNANI_API_KEY is not set. Copy .env.example to .env and add your key.\n")
    print(f"  BhashaBridge AI running at http://{Config.HOST}:{Config.PORT}\n")
    application.run(host=Config.HOST, port=Config.PORT, debug=Config.DEBUG)
