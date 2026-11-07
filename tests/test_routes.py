"""MOCKED tests for the Flask routes. External services are replaced with fakes."""
import io

import pytest

from services.gnani_common import GnaniError

from .conftest import make_wav


class FakePrisma:
    configured = True
    model = "prisma-v2.5"

    def __init__(self, transcript="नमस्ते", error=None):
        self.transcript, self.error, self.calls = transcript, error, []

    def transcribe(self, audio, filename, content_type, language):
        self.calls.append((len(audio), filename, content_type, language))
        if self.error:
            raise self.error
        return {"transcript": self.transcript, "model": "gnani-prisma-v2.5", "request_id": "r1",
                "detected_language_code": None, "truncated": False}


class FakeTimbre:
    configured = True
    model = "timbre-v2.5"

    def __init__(self, error=None):
        self.error, self.calls = error, []

    def synthesize(self, text, language):
        self.calls.append((text, language))
        if self.error:
            raise self.error
        return b"RIFFFAKEWAV", "audio/wav"


def post_audio(client, data, mime="audio/wav", lang="hi-IN", name="r.wav"):
    return client.post("/api/voice/transcribe",
                       data={"audio": (io.BytesIO(data), name, mime), "language": lang},
                       content_type="multipart/form-data")


# ---------------------------------------------------------------- pages
@pytest.mark.parametrize("path", ["/", "/dashboard", "/student", "/about"])
def test_pages_load(client, path):
    r = client.get(path)
    assert r.status_code == 200 and b"BhashaBridge" in r.data


def test_api_key_never_in_pages_or_static(client):
    for path in ["/", "/dashboard", "/static/js/app.js", "/static/js/chat.js", "/static/js/voice.js"]:
        assert b"test-key-not-real" not in client.get(path).data


def test_unknown_route_returns_json_404(client):
    r = client.get("/nope")
    assert r.status_code == 404 and r.get_json()["error"]["code"] == "NOT_FOUND"


# ---------------------------------------------------------------- health / config
def test_health_reports_without_leaking_key(client):
    data = client.get("/api/health").get_json()
    assert data["services"]["prisma"]["configured"] is True
    assert data["services"]["reasoning"]["configured"] is False
    assert "test-key-not-real" not in client.get("/api/health").get_data(as_text=True)


def test_config_lists_five_verified_languages(client):
    langs = [l["code"] for l in client.get("/api/config").get_json()["languages"]]
    assert langs == ["en-IN", "hi-IN", "kn-IN", "ta-IN", "te-IN"]


# ---------------------------------------------------------------- transcription
def test_transcribe_success(app, client, wav_bytes):
    fake = FakePrisma()
    app.extensions["bb"]["prisma"] = fake
    r = post_audio(client, wav_bytes)
    assert r.status_code == 200
    assert r.get_json()["transcript"] == "नमस्ते"
    assert fake.calls[0][1:] == ("recording.wav", "audio/wav", "hi-IN")
    # health badge now shows a real successful call
    assert client.get("/api/health").get_json()["services"]["prisma"]["last_call"] == {"ok": True}


def test_transcribe_webm_is_rejected_because_prisma_does_not_list_it(client):
    r = post_audio(client, b"x" * 1000, mime="audio/webm", name="r.webm")
    assert r.status_code == 415 and r.get_json()["error"]["code"] == "BAD_AUDIO_TYPE"


def test_transcribe_m4a_is_relabelled(app, client):
    fake = FakePrisma()
    app.extensions["bb"]["prisma"] = fake
    post_audio(client, b"x" * 1000, mime="audio/mp4", name="blob")
    assert fake.calls[0][1:3] == ("recording.m4a", "audio/mp4")


def test_transcribe_missing_audio(client):
    r = client.post("/api/voice/transcribe", data={"language": "en-IN"})
    assert r.status_code == 400 and r.get_json()["error"]["code"] == "NO_AUDIO"


def test_transcribe_bad_language(client, wav_bytes):
    r = post_audio(client, wav_bytes, lang="fr-FR")
    assert r.status_code == 400 and r.get_json()["error"]["code"] == "UNSUPPORTED_LANGUAGE"


def test_transcribe_empty_and_corrupt(client):
    assert post_audio(client, b"").get_json()["error"]["code"] == "EMPTY_AUDIO"
    assert post_audio(client, b"not a wav file" * 50).get_json()["error"]["code"] == "BAD_AUDIO"


def test_transcribe_too_long_wav(client):
    r = post_audio(client, make_wav(seconds=31))
    assert r.status_code == 400 and r.get_json()["error"]["code"] == "AUDIO_TOO_LONG"


def test_transcribe_too_large(app, client, wav_bytes, monkeypatch):
    monkeypatch.setattr(app.extensions["bb"]["config"], "MAX_AUDIO_MB", 0)  # any upload exceeds 0 MB
    r = post_audio(client, wav_bytes)
    assert r.status_code == 413 and r.get_json()["error"]["code"] == "AUDIO_TOO_LARGE"


def test_transcribe_no_speech(app, client, wav_bytes):
    app.extensions["bb"]["prisma"] = FakePrisma(transcript="")
    r = post_audio(client, wav_bytes)
    assert r.status_code == 422 and r.get_json()["error"]["code"] == "NO_SPEECH"


def test_transcribe_upstream_failure_returns_friendly_error(app, client, wav_bytes):
    err = GnaniError("Gnani rejected the API key (Prisma).", code="INVALID_API_KEY", http_status=502)
    app.extensions["bb"]["prisma"] = FakePrisma(error=err)
    r = post_audio(client, wav_bytes)
    assert r.status_code == 502 and "API key" in r.get_json()["error"]["message"]
    last = client.get("/api/health").get_json()["services"]["prisma"]["last_call"]
    assert last["ok"] is False


def test_audio_is_not_written_to_disk(app, client, wav_bytes, tmp_path, monkeypatch):
    app.extensions["bb"]["prisma"] = FakePrisma()
    import tempfile
    monkeypatch.setattr(tempfile, "NamedTemporaryFile", lambda *a, **k: pytest.fail("temp file used"))
    assert post_audio(client, wav_bytes).status_code == 200


# ---------------------------------------------------------------- speech
def test_speak_returns_audio(app, client):
    fake = FakeTimbre()
    app.extensions["bb"]["timbre"] = fake
    r = client.post("/api/voice/speak", json={"text": "hello", "language": "ta-IN"})
    assert r.status_code == 200 and r.mimetype == "audio/wav" and r.data == b"RIFFFAKEWAV"
    assert fake.calls == [("hello", "ta-IN")]


def test_speak_validation_and_errors(app, client):
    assert client.post("/api/voice/speak", json={"text": " "}).status_code == 400
    assert client.post("/api/voice/speak", json={"text": "x" * 5000}).status_code == 400
    app.extensions["bb"]["timbre"] = FakeTimbre(GnaniError("Timbre down", code="X", http_status=502))
    r = client.post("/api/voice/speak", json={"text": "hello", "language": "en-IN"})
    assert r.status_code == 502 and r.get_json()["error"]["message"] == "Timbre down"


def test_speak_unconfigured_returns_503(app, client):
    from services.timbre_service import TimbreService
    app.extensions["bb"]["timbre"] = TimbreService("", "https://x")
    r = client.post("/api/voice/speak", json={"text": "hello"})
    assert r.status_code == 503 and r.get_json()["error"]["code"] == "NOT_CONFIGURED"


# ---------------------------------------------------------------- chat + history
def test_chat_faq_fallback_and_history(client, headers):
    r = client.post("/api/chat", json={"message": "How do I find scholarships?", "language": "en-IN"}, headers=headers)
    body = r.get_json()
    assert r.status_code == 200 and body["source"] == "faq" and "scholarship" in body["reply"].lower()
    assert body["notice"]
    hist = client.get("/api/history", headers=headers).get_json()["messages"]
    assert [m["role"] for m in hist] == ["user", "assistant"]
    assert hist[1]["source"] == "faq" and hist[0]["created_at"]


def test_chat_follow_up_history_is_sent_to_llm(app, client, headers):
    captured = {}

    class SpyLLM:
        configured = True
        label = "spy"

        def reply(self, text, language, history=None, mode="assistant"):
            captured.update(text=text, history=history, mode=mode)
            return {"text": "answer", "language": language, "source": "llm", "notice": None}

    app.extensions["bb"]["llm"] = SpyLLM()
    client.post("/api/chat", json={"message": "first question", "language": "hi-IN"}, headers=headers)
    client.post("/api/chat", json={"message": "and a follow-up?", "language": "hi-IN", "mode": "student"}, headers=headers)
    contents = [m["content"] for m in captured["history"]]
    assert contents == ["first question", "answer"] and captured["mode"] == "student"


def test_history_is_per_session_and_clearable(client):
    a, b = {"X-Session-Id": "aaaaaaaaaaaa"}, {"X-Session-Id": "bbbbbbbbbbbb"}
    client.post("/api/chat", json={"message": "library?"}, headers=a)
    assert len(client.get("/api/history", headers=a).get_json()["messages"]) == 2
    assert client.get("/api/history", headers=b).get_json()["messages"] == []
    assert client.delete("/api/history", headers=a).get_json()["removed"] == 2
    assert client.get("/api/history", headers=a).get_json()["messages"] == []


def test_chat_validation(client):
    assert client.post("/api/chat", json={"message": "  "}).status_code == 400
    assert client.post("/api/chat", json={"message": "x" * 1001}).status_code == 400
    assert client.post("/api/chat", data="notjson", content_type="text/plain").status_code == 400


def test_chat_unknown_language_defaults_to_english(app, client):
    r = client.post("/api/chat", json={"message": "library", "language": "xx-XX"})
    assert r.status_code == 200


def test_faq_endpoint(client):
    data = client.get("/api/faq?q=exam&category=exams").get_json()
    assert data["faqs"] and all(f["category"] == "exams" for f in data["faqs"])
    assert "DEMONSTRATION" in data["notice"]
    assert client.get("/api/faq?q=zzzzqqqq").get_json()["faqs"] == []
    assert len(client.get("/api/faq").get_json()["faqs"]) >= 15
