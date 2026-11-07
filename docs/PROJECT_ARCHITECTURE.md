# Project architecture

```
Browser (HTML/CSS/JS)                       Flask backend                         External
─────────────────────                       ─────────────                         ────────
mic → MediaRecorder → WAV 16 kHz  ──POST /api/voice/transcribe──►  prisma_service ──► Gnani Prisma
text box                          ──POST /api/chat─────────────►  llm_service ─────► OpenAI-compatible LLM (optional)
                                                                       │ fallback       └─ or demo FAQ (faq_data.json)
reply bubble ◄──────────────────── JSON {reply, source, notice}  conversation_service ─► SQLite (text only)
▶ Play / Replay  ──POST /api/voice/speak──────────────────────►  timbre_service ──► Gnani Timbre → WAV
```

## Folders

| Path | Role |
|---|---|
| `app.py` | App factory: wires services, registers routes, error handlers, security headers |
| `config.py` | All settings from environment variables; enabled languages and voices |
| `services/gnani_common.py` | Shared HTTP retry + mapping of every documented Gnani error shape to friendly messages |
| `services/prisma_service.py` | Speech-to-text client |
| `services/timbre_service.py` | Text-to-speech client (+ text cleaning for natural speech) |
| `services/llm_service.py` | Reasoning provider adapter + FAQ knowledge base search |
| `services/conversation_service.py` | Chat history in SQLite |
| `routes/voice_routes.py` | `/api/voice/transcribe`, `/api/voice/speak` with validation |
| `routes/chat_routes.py` | `/api/chat`, `/api/history`, `/api/faq` |
| `routes/health_routes.py` | `/api/health`, `/api/config` |
| `database/` | `schema.sql`, `db.py`, `faq_data.json` (editable demo knowledge base) |
| `templates/`, `static/` | Four pages, shared chat widget, CSS, JS (`app.js`, `voice.js`, `chat.js`, `student.js`) |
| `tests/` | Mocked tests + opt-in live tests |

## Key decisions

* **Server-side secrets.** Only `services/*` talk to Gnani, using `GNANI_API_KEY` from the environment. The browser only knows `/api/...` routes on the same origin (so no CORS is configured).
* **Audio never touches disk.** The upload is read into memory, validated (MIME, size, WAV duration), forwarded, and discarded. A test enforces that no temp file is created.
* **Honest status.** `/api/health` reports `configured` separately from `last_call`, so the UI never claims a service works until a real call succeeded.
* **Honest answers.** Each reply stores and displays its `source` (llm / faq / fallback). The system prompt forbids inventing college facts; FAQ entries are labelled demonstration data.
* **Swappable reasoning.** `LLMService` speaks the OpenAI `/chat/completions` protocol, so Gnani Evon (via vLLM/SGLang) or another provider is a configuration change.
* **Sessions without accounts.** The browser generates a random id (localStorage) sent as `X-Session-Id` to separate histories. It is not authentication, which is appropriate for a local demo; add real auth before any public deployment.
* **Validation.** Language whitelist, message length (1000), audio MIME allow-list, size limit (`MAX_AUDIO_MB`), 30 s duration check for WAV. Timeouts for each external call are set in `config.py`.

## Request flow for a spoken question
1. `voice.js` records, converts to WAV, uploads to `/api/voice/transcribe` with the language.
2. Backend validates and calls Prisma; returns the transcript.
3. `chat.js` shows the transcript as the user message and calls `/api/chat`.
4. `llm_service` retrieves matching FAQ entries, calls the LLM (if configured) with the last 8 messages for follow-ups, otherwise answers from the FAQ.
5. The reply is stored and displayed; if "Speak replies aloud" is on, `/api/voice/speak` returns Timbre audio, cached per message for instant replay.

## Extending
* More languages: `config.py` (`LANGUAGES`, `TTS_VOICES_V25`).
* Your own college data: edit `database/faq_data.json`.
* Production use: run behind a real WSGI server (e.g. `waitress`), add authentication and rate limiting, serve over HTTPS.
