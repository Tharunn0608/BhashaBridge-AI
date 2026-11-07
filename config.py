"""Central configuration for BhashaBridge AI.

Every secret and tunable value comes from environment variables (or a local
.env file loaded below). Nothing secret is ever hardcoded in this project.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(_env(name, str(default)))
    except ValueError:
        return default


def _bool(name: str, default: bool = False) -> bool:
    return _env(name, str(default)).lower() in ("1", "true", "yes", "on")


# ---------------------------------------------------------------------------
# Languages
# These five codes are listed in the official Gnani docs for BOTH Prisma
# (speech-to-text) and Timbre (text-to-speech), so they are safe to enable.
# Source: https://docs.gnani.ai/api/STT/speech-to-text.md  (Supported languages)
#         https://docs.gnani.ai/api/TTS/available-voices.md
# ---------------------------------------------------------------------------
LANGUAGES = {
    "en-IN": {"name": "English", "native": "English"},
    "hi-IN": {"name": "Hindi", "native": "हिन्दी"},
    "kn-IN": {"name": "Kannada", "native": "ಕನ್ನಡ"},
    "ta-IN": {"name": "Tamil", "native": "தமிழ்"},
    "te-IN": {"name": "Telugu", "native": "తెలుగు"},
}

# Timbre v2.5 voices are language-specific ("preferred language" per voice in
# the official voice catalog). One voice per supported language:
TTS_VOICES_V25 = {
    "en-IN": "Kaveri",
    "hi-IN": "Nalini",
    "kn-IN": "Saanvi",
    "ta-IN": "Trisha",
    "te-IN": "Suhana",
}
# Timbre v3.0 voices speak all 10 languages, so one voice is enough.
TTS_VOICE_V30 = "Shivani"


class Config:
    # --- Flask / app ---
    HOST = _env("HOST", "127.0.0.1")
    PORT = _int("PORT", 5000)
    DEBUG = _bool("FLASK_DEBUG", False)
    DATABASE_PATH = _env("DATABASE_PATH", str(BASE_DIR / "instance" / "bhashabridge.db"))
    FAQ_PATH = _env("FAQ_PATH", str(BASE_DIR / "database" / "faq_data.json"))

    # --- Audio upload limits ---
    MAX_AUDIO_MB = _int("MAX_AUDIO_MB", 10)
    MAX_CONTENT_LENGTH = (MAX_AUDIO_MB + 2) * 1024 * 1024
    MAX_AUDIO_SECONDS = 30  # Prisma REST limit per the official docs

    # --- Gnani (backend only - the key never reaches the browser) ---
    GNANI_API_KEY = _env("GNANI_API_KEY")
    GNANI_BASE_URL = _env("GNANI_BASE_URL", "https://api.vachana.ai").rstrip("/")
    GNANI_TIMEOUT = _float("GNANI_TIMEOUT", 60.0)
    GNANI_RETRIES = _int("GNANI_RETRIES", 1)
    # "prisma-v2.5" is the documented default (the model field is omitted).
    # Set to "prisma-v3.0" to use Prisma v3.0.
    STT_MODEL = _env("GNANI_STT_MODEL", "prisma-v2.5")
    STT_FORMAT = _env("GNANI_STT_FORMAT", "transcribe")  # transcribe = numbers as digits
    TTS_MODEL = _env("GNANI_TTS_MODEL", "timbre-v2.5")
    TTS_SPEED = _float("GNANI_TTS_SPEED", 1.0)  # documented range 0.85 - 1.15
    TTS_SAMPLE_RATE = _int("GNANI_TTS_SAMPLE_RATE", 24000)
    TTS_MAX_CHARS = _int("TTS_MAX_CHARS", 600)

    # --- Reasoning provider: any OpenAI-compatible /chat/completions server ---
    # e.g. a self-hosted Gnani Evon (vLLM / SGLang) or another provider.
    LLM_BASE_URL = _env("LLM_BASE_URL")
    LLM_API_KEY = _env("LLM_API_KEY")
    LLM_MODEL = _env("LLM_MODEL")
    LLM_LABEL = _env("LLM_LABEL", "Reasoning model")
    LLM_TIMEOUT = _float("LLM_TIMEOUT", 45.0)
    LLM_DISABLE_THINKING = _bool("LLM_DISABLE_THINKING", False)
    LLM_MAX_TOKENS = _int("LLM_MAX_TOKENS", 400)

    APP_NAME = "BhashaBridge AI"
    APP_VERSION = "1.0.0"


def voice_for(language: str, model: str) -> str:
    """Pick the Timbre voice for a language (override with GNANI_VOICE_HI_IN etc.)."""
    override = _env("GNANI_VOICE_" + language.replace("-", "_").upper())
    if override:
        return override
    if model == "timbre-v3.0":
        return TTS_VOICE_V30
    return TTS_VOICES_V25.get(language, TTS_VOICES_V25["en-IN"])
