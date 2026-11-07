"""Gnani Timbre - text to speech (REST).

Endpoint, headers and fields verified against the official docs:
https://docs.gnani.ai/api/TTS/tts-inference.md
https://docs.gnani.ai/api/TTS/available-voices.md

    POST https://api.vachana.ai/api/v1/tts/inference   (JSON)
    Header : X-API-Key-ID: <API key>
    Body   : text, voice, model ("timbre-v2.5" | "timbre-v3.0"), language,
             speed (0.85 - 1.15), audio_config {sample_rate, num_channels,
             sample_width, encoding, container}
    Success: 200 with raw binary audio (Content-Type audio/wav for wav)
    Errors : flat JSON {"success": false, "message": "...", "status_code": N}
"""
import re

from config import voice_for

from .gnani_common import GnaniError, raise_for_response, request_with_retry

_URL_RE = re.compile(r"https?://\S+")
_MD_RE = re.compile(r"[*_`#>~|]+")


def clean_for_speech(text: str, max_chars: int) -> str:
    """Strip markdown/URLs and cut at a sentence boundary so speech sounds natural."""
    text = _URL_RE.sub(" ", text or "")
    text = _MD_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars]
    # prefer ending on a sentence stop (. ? ! or the Devanagari danda)
    stops = [cut.rfind(ch) for ch in ".?!।"]
    best = max(stops)
    if best > max_chars * 0.5:
        return cut[: best + 1]
    return cut.rsplit(" ", 1)[0]


class TimbreService:
    def __init__(self, api_key, base_url, model="timbre-v2.5", speed=1.0,
                 sample_rate=24000, max_chars=600, timeout=60.0, retries=1):
        self.api_key = api_key
        self.url = f"{base_url}/api/v1/tts/inference"
        self.model = model
        self.speed = speed
        self.sample_rate = sample_rate
        self.max_chars = max_chars
        self.timeout = timeout
        self.retries = retries

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def synthesize(self, text: str, language: str):
        """Return (audio_bytes, content_type) for the given text."""
        if not self.configured:
            raise GnaniError("GNANI_API_KEY is not set. Add it to your .env file and restart.",
                             code="NOT_CONFIGURED", http_status=503)
        spoken = clean_for_speech(text, self.max_chars)
        if not spoken:
            raise GnaniError("There is no text to speak.", code="EMPTY_TEXT", http_status=400)

        payload = {
            "text": spoken,
            "voice": voice_for(language, self.model),
            "model": self.model,
            "language": language,
            "speed": self.speed,
            "audio_config": {
                "sample_rate": self.sample_rate,
                "num_channels": 1,
                "sample_width": 2,
                "encoding": "linear_pcm",
                "container": "wav",
            },
        }
        resp = request_with_retry(
            "POST", self.url,
            headers={"X-API-Key-ID": self.api_key, "Content-Type": "application/json"},
            json=payload,
            timeout=self.timeout,
            retries=self.retries,
            service="Voice synthesis (Timbre)",
        )
        if not resp.ok:
            raise_for_response(resp, "Voice synthesis (Timbre)")

        ctype = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if ctype == "application/json" or not resp.content:
            raise GnaniError("Timbre did not return audio.", code="BAD_RESPONSE")
        return resp.content, (ctype if ctype.startswith("audio/") else "audio/wav")
