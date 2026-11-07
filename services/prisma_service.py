"""Gnani Prisma - speech to text (REST).

Endpoint, headers and fields verified against the official docs:
https://docs.gnani.ai/api/STT/speech-to-text.md

    POST https://api.vachana.ai/stt/v3        (multipart/form-data)
    Header : X-API-Key-ID: <API key>
    Fields : audio_file (required), language_code (required),
             model (optional: "prisma-v3.0"; omitted = Prisma v2.5),
             format (optional: verbatim | transcribe)
    Limits : max 30 s audio; WAV, MP3, OGG, FLAC, AAC, M4A
    Success: {"success": true, "transcript": "...", ...}
"""
from .gnani_common import GnaniError, raise_for_response, request_with_retry


class PrismaService:
    def __init__(self, api_key, base_url, model="prisma-v2.5", stt_format="transcribe",
                 timeout=60.0, retries=1):
        self.api_key = api_key
        self.url = f"{base_url}/stt/v3"
        self.model = model
        self.stt_format = stt_format
        self.timeout = timeout
        self.retries = retries

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def transcribe(self, audio: bytes, filename: str, content_type: str, language_code: str) -> dict:
        if not self.configured:
            raise GnaniError("GNANI_API_KEY is not set. Add it to your .env file and restart.",
                             code="NOT_CONFIGURED", http_status=503)

        data = {"language_code": language_code}
        if self.stt_format:
            data["format"] = self.stt_format
        # Prisma v2.5 is the API default, so the model field is only sent for others.
        if self.model and self.model != "prisma-v2.5":
            data["model"] = self.model

        resp = request_with_retry(
            "POST", self.url,
            headers={"X-API-Key-ID": self.api_key},
            files={"audio_file": (filename, audio, content_type)},
            data=data,
            timeout=self.timeout,
            retries=self.retries,
            service="Speech recognition (Prisma)",
        )
        if not resp.ok:
            raise_for_response(resp, "Speech recognition (Prisma)")

        try:
            body = resp.json()
        except ValueError:
            raise GnaniError("Prisma returned an unreadable response.", code="BAD_RESPONSE")
        if not isinstance(body, dict) or body.get("success") is False \
                or not isinstance(body.get("transcript"), str):
            raise GnaniError("Prisma returned an unexpected response.", code="BAD_RESPONSE")

        return {
            "transcript": body["transcript"].strip(),
            "model": body.get("model", self.model),
            "request_id": body.get("request_id"),
            "detected_language_code": body.get("detected_language_code"),
            "truncated": bool(body.get("truncated", False)),
        }
