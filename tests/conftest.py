"""Shared pytest fixtures. All tests here use MOCKED external APIs - no network, no real key."""
import io
import struct
import sys
import wave
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app  # noqa: E402
from config import Config  # noqa: E402


class TestConfig(Config):
    GNANI_API_KEY = "test-key-not-real"
    GNANI_RETRIES = 0
    LLM_BASE_URL = ""
    LLM_MODEL = ""


@pytest.fixture()
def app(tmp_path):
    TestConfig.DATABASE_PATH = str(tmp_path / "test.db")
    application = create_app(TestConfig, {"TESTING": True, "DATABASE_PATH": TestConfig.DATABASE_PATH})
    return application


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def headers():
    return {"X-Session-Id": "testsession12345678"}


def make_wav(seconds=1.0, rate=16000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(struct.pack("<h", 1000) * int(seconds * rate))
    return buf.getvalue()


@pytest.fixture()
def wav_bytes():
    return make_wav()


class FakeResponse:
    """Minimal stand-in for requests.Response."""

    def __init__(self, status=200, json_body=None, content=b"", headers=None):
        self.status_code = status
        self._json = json_body
        self.content = content
        self.headers = headers or {}
        self.text = str(json_body) if json_body is not None else ""

    @property
    def ok(self):
        return 200 <= self.status_code < 300

    def json(self):
        if self._json is None:
            raise ValueError("no json")
        return self._json

    def raise_for_status(self):
        if not self.ok:
            import requests
            raise requests.HTTPError(f"HTTP {self.status_code}")
