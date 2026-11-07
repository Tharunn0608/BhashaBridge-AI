"""LIVE integration tests - these call the REAL Gnani APIs.

They are SKIPPED automatically unless GNANI_API_KEY is set (in .env or your shell),
so the normal test run stays offline. They may consume a small amount of Gnani credit.

Run them with:
    pytest tests/test_live_integration.py -v -s

What they prove (only when they pass on your machine with your key):
  * Timbre really synthesises audio for each of the 5 enabled languages
  * Prisma really transcribes that audio (round trip: text -> speech -> text)
  * The full Flask pipeline works end to end
"""
import os
import re

import pytest

from config import Config, LANGUAGES

pytestmark = pytest.mark.skipif(
    not (os.getenv("GNANI_API_KEY") or Config.GNANI_API_KEY),
    reason="GNANI_API_KEY not set - live tests skipped (mocked tests cover the rest)",
)

PHRASES = {
    "en-IN": "Hello, how can I prepare for my exams?",
    "hi-IN": "नमस्ते, मैं अपनी परीक्षा की तैयारी कैसे करूँ?",
    "kn-IN": "ನಮಸ್ಕಾರ, ನಾನು ಪರೀಕ್ಷೆಗೆ ಹೇಗೆ ತಯಾರಿ ಮಾಡಬೇಕು?",
    "ta-IN": "வணக்கம், தேர்வுக்கு நான் எப்படி தயாராவது?",
    "te-IN": "నమస్కారం, నేను పరీక్షకు ఎలా సిద్ధం కావాలి?",
}


@pytest.fixture(scope="module")
def services():
    from services.prisma_service import PrismaService
    from services.timbre_service import TimbreService
    key = os.getenv("GNANI_API_KEY") or Config.GNANI_API_KEY
    return (
        PrismaService(key, Config.GNANI_BASE_URL, Config.STT_MODEL, Config.STT_FORMAT, retries=2),
        TimbreService(key, Config.GNANI_BASE_URL, Config.TTS_MODEL, Config.TTS_SPEED,
                      Config.TTS_SAMPLE_RATE, Config.TTS_MAX_CHARS, retries=2),
    )


def _words(s):
    return set(re.findall(r"\w+", s.lower()))


@pytest.mark.parametrize("lang", list(LANGUAGES))
def test_live_timbre_generates_audio(services, lang):
    _, timbre = services
    audio, ctype = timbre.synthesize(PHRASES[lang], lang)
    assert ctype.startswith("audio/") and audio[:4] == b"RIFF" and len(audio) > 2000
    print(f"\n[{lang}] Timbre returned {len(audio)} bytes of {ctype}")


@pytest.mark.parametrize("lang", list(LANGUAGES))
def test_live_round_trip_timbre_to_prisma(services, lang):
    """Speak a phrase with Timbre, then transcribe it with Prisma. Expect overlapping words."""
    prisma, timbre = services
    audio, _ = timbre.synthesize(PHRASES[lang], lang)
    # Timbre outputs WAV at 24 kHz; Prisma accepts 8-44.1 kHz WAV directly.
    out = prisma.transcribe(audio, "roundtrip.wav", "audio/wav", lang)
    print(f"\n[{lang}] said: {PHRASES[lang]}\n[{lang}] heard: {out['transcript']}")
    assert out["transcript"], "Prisma returned an empty transcript"
    overlap = _words(PHRASES[lang]) & _words(out["transcript"])
    assert overlap, "Transcript shares no words with the spoken phrase"


def test_live_full_pipeline_through_flask(services):
    """Audio in -> /api/voice/transcribe -> /api/chat -> /api/voice/speak."""
    import io
    from app import create_app
    _, timbre = services
    audio, _ = timbre.synthesize(PHRASES["en-IN"], "en-IN")
    client = create_app(Config, {"TESTING": True}).test_client()
    t = client.post("/api/voice/transcribe",
                    data={"audio": (io.BytesIO(audio), "x.wav", "audio/wav"), "language": "en-IN"},
                    content_type="multipart/form-data")
    assert t.status_code == 200, t.get_json()
    transcript = t.get_json()["transcript"]
    c = client.post("/api/chat", json={"message": transcript, "language": "en-IN"})
    assert c.status_code == 200 and c.get_json()["reply"]
    s = client.post("/api/voice/speak", json={"text": c.get_json()["reply"], "language": "en-IN"})
    assert s.status_code == 200 and s.data[:4] == b"RIFF"
    print(f"\nTranscript: {transcript}\nReply ({c.get_json()['source']}): {c.get_json()['reply'][:80]}")
