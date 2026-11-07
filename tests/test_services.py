"""MOCKED tests for the service layer (Prisma, Timbre, LLM/FAQ, conversations)."""
import json

import pytest
import requests

from services import gnani_common, llm_service, prisma_service, timbre_service
from services.conversation_service import ConversationService
from services.gnani_common import GnaniError
from services.llm_service import FaqKnowledgeBase, LLMService
from services.prisma_service import PrismaService
from services.timbre_service import TimbreService, clean_for_speech

from .conftest import FakeResponse

BASE = "https://api.vachana.ai"


# ---------------------------------------------------------------- Prisma
def test_prisma_builds_documented_request(monkeypatch):
    seen = {}

    def fake(method, url, **kw):
        seen.update(method=method, url=url, **kw)
        return FakeResponse(200, {"success": True, "transcript": " नमस्ते ", "model": "gnani-prisma-v2.5"})

    monkeypatch.setattr(gnani_common.requests, "request", fake)
    svc = PrismaService("KEY", BASE, "prisma-v2.5", "transcribe", retries=0)
    out = svc.transcribe(b"RIFFdata", "recording.wav", "audio/wav", "hi-IN")

    assert seen["method"] == "POST" and seen["url"] == f"{BASE}/stt/v3"
    assert seen["headers"] == {"X-API-Key-ID": "KEY"}
    assert seen["data"] == {"language_code": "hi-IN", "format": "transcribe"}   # no model => v2.5
    assert "audio_file" in seen["files"]
    assert out["transcript"] == "नमस्ते"


def test_prisma_v3_sends_model_field(monkeypatch):
    seen = {}
    monkeypatch.setattr(gnani_common.requests, "request",
                        lambda m, u, **kw: seen.update(kw) or FakeResponse(200, {"success": True, "transcript": "hi"}))
    PrismaService("K", BASE, "prisma-v3.0", "", retries=0).transcribe(b"x", "a.wav", "audio/wav", "en-IN")
    assert seen["data"]["model"] == "prisma-v3.0"


@pytest.mark.parametrize("status,body,expect_status,expect_text", [
    (401, {"detail": {"error_code": "INVALID_API_KEY", "message": "Unauthorized", "status_code": 401}}, 502, "API key"),
    (402, {"detail": {"message": "credit"}}, 502, "credits"),
    (429, {"detail": {"error_code": "RATE_LIMITED", "message": "x", "status_code": 429}}, 429, "rate limiting"),
    (400, {"success": False, "error": {"type": "MAX_AUDIO_DURATION_EXCEEDED", "message": "too long"}}, 422, "too long"),
    (422, {"detail": [{"loc": ["body", "language_code"], "msg": "Field required"}]}, 422, "Field required"),
    (504, {"error": "Gateway Timeout", "code": "UPSTREAM_TIMEOUT", "message": "timeout"}, 504, "timed out"),
    (500, {"success": False, "error": {"type": "INTERNAL_SERVER_ERROR", "message": "x"}}, 502, "unavailable"),
])
def test_prisma_maps_documented_errors(monkeypatch, status, body, expect_status, expect_text):
    monkeypatch.setattr(gnani_common.requests, "request", lambda *a, **k: FakeResponse(status, body))
    with pytest.raises(GnaniError) as exc:
        PrismaService("K", BASE, retries=0).transcribe(b"x", "a.wav", "audio/wav", "hi-IN")
    assert exc.value.http_status == expect_status
    assert expect_text.lower() in exc.value.message.lower()


def test_prisma_rejects_malformed_success(monkeypatch):
    monkeypatch.setattr(gnani_common.requests, "request", lambda *a, **k: FakeResponse(200, {"success": True}))
    with pytest.raises(GnaniError) as exc:
        PrismaService("K", BASE, retries=0).transcribe(b"x", "a.wav", "audio/wav", "hi-IN")
    assert exc.value.code == "BAD_RESPONSE"


def test_prisma_without_key_does_not_call_network(monkeypatch):
    monkeypatch.setattr(gnani_common.requests, "request", lambda *a, **k: pytest.fail("network used"))
    with pytest.raises(GnaniError) as exc:
        PrismaService("", BASE).transcribe(b"x", "a.wav", "audio/wav", "hi-IN")
    assert exc.value.code == "NOT_CONFIGURED"


def test_prisma_connection_error_is_friendly(monkeypatch):
    def boom(*a, **k):
        raise requests.ConnectionError("dns")
    monkeypatch.setattr(gnani_common.requests, "request", boom)
    with pytest.raises(GnaniError) as exc:
        PrismaService("K", BASE, retries=0).transcribe(b"x", "a.wav", "audio/wav", "hi-IN")
    assert "internet" in exc.value.message.lower()


def test_retry_on_429_then_success(monkeypatch):
    calls = []

    def seq(*a, **k):
        calls.append(1)
        return FakeResponse(429, {"detail": {}}) if len(calls) == 1 else FakeResponse(200, {"success": True, "transcript": "ok"})

    monkeypatch.setattr(gnani_common.requests, "request", seq)
    monkeypatch.setattr(gnani_common.time, "sleep", lambda s: None)
    out = PrismaService("K", BASE, retries=1).transcribe(b"x", "a.wav", "audio/wav", "en-IN")
    assert out["transcript"] == "ok" and len(calls) == 2


# ---------------------------------------------------------------- Timbre
def test_timbre_builds_documented_request(monkeypatch):
    seen = {}

    def fake(method, url, **kw):
        seen.update(url=url, **kw)
        return FakeResponse(200, content=b"RIFFxxxx", headers={"Content-Type": "audio/wav"})

    monkeypatch.setattr(gnani_common.requests, "request", fake)
    audio, ctype = TimbreService("KEY", BASE, "timbre-v2.5", retries=0).synthesize("नमस्ते", "hi-IN")

    assert seen["url"] == f"{BASE}/api/v1/tts/inference"
    assert seen["headers"]["X-API-Key-ID"] == "KEY"
    body = seen["json"]
    assert body["model"] == "timbre-v2.5" and body["voice"] == "Nalini" and body["language"] == "hi-IN"
    assert body["audio_config"]["container"] == "wav" and body["audio_config"]["encoding"] == "linear_pcm"
    assert 0.85 <= body["speed"] <= 1.15
    assert audio == b"RIFFxxxx" and ctype == "audio/wav"


@pytest.mark.parametrize("lang,voice", [("en-IN", "Kaveri"), ("hi-IN", "Nalini"), ("kn-IN", "Saanvi"),
                                         ("ta-IN", "Trisha"), ("te-IN", "Suhana")])
def test_timbre_voice_per_language(monkeypatch, lang, voice):
    seen = {}
    monkeypatch.setattr(gnani_common.requests, "request",
                        lambda m, u, **kw: seen.update(kw) or FakeResponse(200, content=b"A", headers={"Content-Type": "audio/wav"}))
    TimbreService("K", BASE, retries=0).synthesize("hello", lang)
    assert seen["json"]["voice"] == voice


def test_timbre_v3_uses_multilingual_voice(monkeypatch):
    seen = {}
    monkeypatch.setattr(gnani_common.requests, "request",
                        lambda m, u, **kw: seen.update(kw) or FakeResponse(200, content=b"A", headers={"Content-Type": "audio/wav"}))
    TimbreService("K", BASE, "timbre-v3.0", retries=0).synthesize("hello", "ta-IN")
    assert seen["json"]["voice"] == "Shivani" and seen["json"]["model"] == "timbre-v3.0"


def test_timbre_flat_error_body(monkeypatch):
    body = {"success": False, "message": "Voice 'x' not supported", "status_code": 400}
    monkeypatch.setattr(gnani_common.requests, "request", lambda *a, **k: FakeResponse(400, body))
    with pytest.raises(GnaniError) as exc:
        TimbreService("K", BASE, retries=0).synthesize("hello", "en-IN")
    assert "not supported" in exc.value.message


def test_timbre_json_instead_of_audio_is_error(monkeypatch):
    monkeypatch.setattr(gnani_common.requests, "request",
                        lambda *a, **k: FakeResponse(200, {"x": 1}, content=b"{}", headers={"Content-Type": "application/json"}))
    with pytest.raises(GnaniError):
        TimbreService("K", BASE, retries=0).synthesize("hello", "en-IN")


def test_clean_for_speech_strips_markdown_and_truncates():
    text = "**Hello** see https://example.com now. " + ("Another sentence here. " * 60)
    out = clean_for_speech(text, 100)
    assert "*" not in out and "http" not in out and len(out) <= 100 and out.endswith(".")


# ---------------------------------------------------------------- FAQ + LLM
@pytest.fixture()
def kb(tmp_path):
    p = tmp_path / "faq.json"
    p.write_text(json.dumps({"_notice": "demo", "categories": [{"id": "exams", "name": "Exams"}], "faqs": [
        {"id": "a", "category": "exams", "question": "What do I need on exam day?", "answer": "Hall ticket.",
         "keywords": ["exam day", "hall ticket", "ಹಾಲ್ ಟಿಕೆಟ್"]},
        {"id": "b", "category": "campus", "question": "How do I use the library?", "answer": "Bring ID.",
         "keywords": ["library"]},
    ]}), encoding="utf-8")
    return FaqKnowledgeBase(p)


def test_faq_search_english_and_indic(kb):
    assert kb.search("what do i need for exam day")[0]["id"] == "a"
    assert kb.search("ಹಾಲ್ ಟಿಕೆಟ್ ಎಲ್ಲಿ")[0]["id"] == "a"
    assert kb.search("library timings")[0]["id"] == "b"
    assert kb.search("quantum physics", min_score=1) == []
    assert kb.search("", category="exams")[0]["id"] == "a"


def test_llm_falls_back_to_faq_when_unconfigured(kb):
    svc = LLMService("", "", "", "x", 5, 100, False, kb)
    r = svc.reply("tell me about the library", "en-IN")
    assert r["source"] == "faq" and "Bring ID" in r["text"] and r["notice"]


def test_llm_unmatched_question_is_honest_fallback(kb):
    r = LLMService("", "", "", "x", 5, 100, False, kb).reply("what is the meaning of life", "en-IN")
    assert r["source"] == "fallback"


def test_llm_uses_provider_and_strips_thinking(kb, monkeypatch):
    seen = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        seen.update(url=url, json=json, headers=headers)
        return FakeResponse(200, {"choices": [{"message": {"content": "<think>secret</think>**Hello** there"}}]})

    monkeypatch.setattr(llm_service.requests, "post", fake_post)
    svc = LLMService("http://localhost:8000/v1", "tok", "gnani-evon-v3.3", "Evon", 5, 100, True, kb)
    r = svc.reply("hi", "hi-IN", history=[{"role": "user", "content": "earlier"}])
    assert r["source"] == "llm" and r["text"] == "Hello there"
    assert seen["url"] == "http://localhost:8000/v1/chat/completions"
    assert seen["headers"]["Authorization"] == "Bearer tok"
    assert seen["json"]["chat_template_kwargs"] == {"enable_thinking": False}
    assert seen["json"]["messages"][0]["role"] == "system" and "Hindi" in seen["json"]["messages"][0]["content"]
    assert any(m["content"] == "earlier" for m in seen["json"]["messages"])


def test_llm_failure_falls_back_with_notice(kb, monkeypatch):
    def boom(*a, **k):
        raise requests.ConnectionError("down")
    monkeypatch.setattr(llm_service.requests, "post", boom)
    r = LLMService("http://x/v1", "", "m", "L", 5, 100, False, kb).reply("library", "en-IN")
    assert r["source"] == "faq" and "unavailable" in r["notice"]


# ---------------------------------------------------------------- conversations
def test_conversation_roundtrip_and_isolation(tmp_path):
    from database.db import init_db
    path = str(tmp_path / "c.db")
    init_db(path)
    svc = ConversationService(path)
    svc.add("s1", "user", "hello", "en-IN")
    svc.add("s1", "assistant", "hi", "en-IN", "faq")
    svc.add("s2", "user", "other", "en-IN")
    assert [m["content"] for m in svc.history("s1")] == ["hello", "hi"]
    assert svc.clear("s1") == 2
    assert svc.history("s1") == [] and len(svc.history("s2")) == 1
