# Testing report

**Honest summary:** everything that can be verified without a Gnani API key was verified. The **live Gnani calls were NOT executed during development**, because the build environment could not reach `api.vachana.ai` (connection failed) and no API key was available. The live tests are included and ready for you to run. Until you do, "Prisma transcribes real audio" and "Timbre generates real audio" are **implemented to the official documentation but not yet proven against the real service**.

Legend: ✅ verified · 🟡 verified against a local mock only · ⏳ needs your key (run on your machine)

## A. Automated mocked tests: `pytest`
Result at packaging time: **57 passed, 11 skipped** (the 11 skipped are the live tests, which skip without a key).

* `tests/test_services.py`: request construction matches the documented endpoints, headers, fields and voices for Prisma and Timbre; every documented error shape (401, 402, 429, 400, 422, 504, 5xx) maps to a friendly message; retry on 429; no network call without a key; FAQ search (English + Kannada keywords); LLM adapter (OpenAI-style request, thinking-trace stripping, fallback on failure); conversation storage and per-session isolation.
* `tests/test_routes.py`: pages load; the API key never appears in pages or static files; audio validation (type, empty, corrupt, too long, too large); WebM rejected because Prisma does not list it; M4A relabelling; upstream failures surface as readable errors and flip the health badge; audio never written to disk; chat, follow-up history, history clearing, FAQ endpoint, input validation.

These tests use **fake** Gnani responses. They prove our code builds correct requests and handles documented responses, not that Gnani's servers behave as documented.

## B. Real-browser test against a local MOCK server 🟡
A scripted Chromium (Playwright, fake microphone device) drove the real UI while the backend pointed to a local mock of Gnani and an OpenAI-compatible LLM:

| Check | Result |
|---|---|
| Homepage, assistant, student and about pages load | ✅ |
| Language selector lists exactly en/hi/kn/ta/te | ✅ |
| Typed question → reasoning layer → reply bubble with source tag | ✅ |
| Mic start/stop, recording animation, processing spinner | ✅ |
| Recorded clip arrives at the (mock) Prisma as **valid 16 kHz mono 16-bit WAV**, with `language_code` and `format` set correctly | ✅ |
| Transcript appears as the user message, then the reply | ✅ |
| Follow-up question sends earlier messages to the reasoning model | ✅ |
| Reply sent to the (mock) Timbre with the right voice/model/language; Play → Replay uses cached audio | ✅ |
| Conversation survives reload; Clear empties it | ✅ |
| Health badge goes "Ready" → "All working" only after calls succeed | ✅ |
| Student FAQ search and category filters | ✅ |
| Mobile (390 px) and desktop (1360 px) layouts, no horizontal overflow (a real overflow bug was found and fixed) | ✅ |

Not covered: real microphones/speech, Safari and Firefox, screen readers, real audio playback quality.

## C. Live Gnani integration tests ⏳
Not run by the author of this build. To run them with your key:

```
pytest tests/test_live_integration.py -v -s
```
They (1) synthesise a phrase in each of the 5 languages with Timbre, (2) transcribe that audio with Prisma and check the words overlap (a round trip), and (3) run the full Flask pipeline. They may use a little of your Gnani credit. Record your results here after running:

| Test | Your result |
|---|---|
| Timbre audio, 5 languages | |
| Prisma round trip, 5 languages | |
| Full pipeline | |

## D. Error handling checks
| Scenario | Verified how |
|---|---|
| No API key configured | Mocked + manual: friendly 503 message, app still runs |
| Invalid key (401), no credit (402/403), rate limit (429), timeout (504), server error | Mocked: messages mapped per official error reference |
| Gnani unreachable | Mocked ConnectionError → "Check your internet connection" |
| Reasoning model down | Mocked: falls back to FAQ with a visible notice |
| Microphone denied / missing / insecure origin | Code paths with clear messages; not exercised with real denial |

## E. Known limitations
* Gnani REST STT limits clips to 30 s; the app auto-stops at 28 s.
* Some Gnani accounts allow one active request at a time; very rapid use may show a "rate limit" message.
* No public hosted Evon endpoint was documented, so Evon is optional (self-host) and not demonstrated here.
* FAQ data is demonstration content. Replace it with verified college information before real use.
* Sessions are anonymous browser IDs, not authentication.
