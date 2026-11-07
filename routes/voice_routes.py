"""Voice endpoints: speech-to-text (Prisma) and text-to-speech (Timbre)."""
import io
import wave

from flask import Blueprint, Response, request

from config import LANGUAGES
from services.gnani_common import GnaniError

from .helpers import gnani_error_response, json_error, services, valid_language

bp = Blueprint("voice", __name__, url_prefix="/api/voice")

# MIME type -> (file name to send to Gnani, MIME to send). Gnani decides format from
# the file extension and supports WAV, MP3, OGG, FLAC, AAC, M4A (official docs).
ALLOWED_AUDIO = {
    "audio/wav": ("recording.wav", "audio/wav"),
    "audio/x-wav": ("recording.wav", "audio/wav"),
    "audio/wave": ("recording.wav", "audio/wav"),
    "audio/mpeg": ("recording.mp3", "audio/mpeg"),
    "audio/mp3": ("recording.mp3", "audio/mpeg"),
    "audio/ogg": ("recording.ogg", "audio/ogg"),
    "audio/flac": ("recording.flac", "audio/flac"),
    "audio/x-flac": ("recording.flac", "audio/flac"),
    "audio/aac": ("recording.aac", "audio/aac"),
    "audio/mp4": ("recording.m4a", "audio/mp4"),
    "audio/x-m4a": ("recording.m4a", "audio/mp4"),
    "audio/m4a": ("recording.m4a", "audio/mp4"),
}


def _wav_seconds(data: bytes):
    """Duration of a WAV file, or None if it is not a readable WAV."""
    try:
        with wave.open(io.BytesIO(data)) as w:
            return w.getnframes() / float(w.getframerate())
    except (wave.Error, EOFError):
        return None


@bp.post("/transcribe")
def transcribe():
    bb = services()
    cfg = bb["config"]
    file = request.files.get("audio")
    if file is None:
        return json_error("No audio was received. Please record again.", 400, "NO_AUDIO")

    language = request.form.get("language", "en-IN")
    if language not in LANGUAGES:
        return json_error("That language is not supported.", 400, "UNSUPPORTED_LANGUAGE")

    mime = (file.mimetype or "").split(";")[0].strip().lower()
    if mime not in ALLOWED_AUDIO:
        return json_error(
            "Unsupported audio format. Use WAV, MP3, OGG, FLAC, AAC or M4A.", 415, "BAD_AUDIO_TYPE")

    # Read at most limit+1 bytes so oversized uploads are rejected cheaply.
    limit = cfg.MAX_AUDIO_MB * 1024 * 1024
    data = file.read(limit + 1)
    if len(data) > limit:
        return json_error(f"Audio is too large (max {cfg.MAX_AUDIO_MB} MB).", 413, "AUDIO_TOO_LARGE")
    if len(data) < 200:
        return json_error("The recording is empty. Please speak and try again.", 400, "EMPTY_AUDIO")

    if mime in ("audio/wav", "audio/x-wav", "audio/wave"):
        seconds = _wav_seconds(data)
        if seconds is None:
            return json_error("The WAV file could not be read.", 400, "BAD_AUDIO")
        if seconds > cfg.MAX_AUDIO_SECONDS:
            return json_error(
                f"Recording is {seconds:.0f}s long. The maximum is {cfg.MAX_AUDIO_SECONDS} seconds.",
                400, "AUDIO_TOO_LONG")

    name, send_mime = ALLOWED_AUDIO[mime]
    try:
        # The audio lives only in memory for this request - it is never written to disk.
        result = bb["prisma"].transcribe(data, name, send_mime, language)
    except GnaniError as exc:
        return gnani_error_response(exc)
    bb["status"].record_ok("prisma")

    if not result["transcript"]:
        return json_error("I could not hear any speech. Please try again closer to the microphone.",
                          422, "NO_SPEECH")
    return {"ok": True, **result, "language": language}


@bp.post("/speak")
def speak():
    bb = services()
    body = request.get_json(silent=True) or {}
    text = (body.get("text") or "").strip()
    if not text:
        return json_error("There is no text to speak.", 400, "EMPTY_TEXT")
    if len(text) > 4000:
        return json_error("Text is too long.", 400, "TEXT_TOO_LONG")
    language = valid_language(body.get("language"))

    try:
        audio, ctype = bb["timbre"].synthesize(text, language)
    except GnaniError as exc:
        return gnani_error_response(exc)
    bb["status"].record_ok("timbre")
    return Response(audio, mimetype=ctype, headers={"Cache-Control": "no-store"})
