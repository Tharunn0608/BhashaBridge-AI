# API setup and integration notes

Everything below was checked against the official Gnani documentation (docs.gnani.ai) while building this project.

## 1. Get your Gnani API key

1. Sign in at <https://app.gnani.ai/> and create an API key (the quick-start says to sign up on the Gnani API platform).
2. Copy `.env.example` to `.env` and set:
   ```
   GNANI_API_KEY=paste_your_key_here
   ```
3. Restart the app. The key is read by the Flask backend only. It is never sent to the browser, never logged, and `.env` is git-ignored.

> Never paste the key into source code, a README, a screenshot or a LinkedIn post. If you ever expose it, revoke it in the dashboard and create a new one.

## 2. Endpoints used

| Purpose | Request | Notes |
|---|---|---|
| Speech to text (Prisma) | `POST https://api.vachana.ai/stt/v3` multipart: `audio_file`, `language_code`, optional `format`, optional `model` | Header `X-API-Key-ID`. Max 30 s. WAV, MP3, OGG, FLAC, AAC, M4A. Returns `{"success": true, "transcript": "..."}` |
| Text to speech (Timbre) | `POST https://api.vachana.ai/api/v1/tts/inference` JSON: `text`, `voice`, `model`, `language`, `speed`, `audio_config` | Header `X-API-Key-ID`. Returns raw WAV bytes. Voices belong to one model each. |

Code: `services/prisma_service.py`, `services/timbre_service.py`, shared error handling in `services/gnani_common.py`.

### Languages enabled
`en-IN`, `hi-IN`, `kn-IN`, `ta-IN`, `te-IN`: listed in the official docs for **both** Prisma and Timbre. Prisma and Timbre also list Bengali, Gujarati, Malayalam, Marathi and Punjabi. To add one, add it to `LANGUAGES` and `TTS_VOICES_V25` in `config.py` (pick a voice from the official voice catalog).

### Voices (Timbre v2.5, one preferred voice per language)
English `Kaveri` · Hindi `Nalini` · Kannada `Saanvi` · Tamil `Trisha` · Telugu `Suhana`.
Override any of them in `.env`, for example `GNANI_VOICE_HI_IN=Deepak`. Switching `GNANI_TTS_MODEL=timbre-v3.0` uses the multilingual voice `Shivani` for all languages.

### Why the browser converts audio to WAV
Chrome records WebM, which is **not** in Prisma's list of supported formats. `static/js/voice.js` therefore decodes the recording with the Web Audio API and re-encodes it as 16 kHz mono 16-bit WAV in memory before upload. Firefox (OGG) and Safari (MP4/M4A) fall back to their native formats, which Prisma accepts.

## 3. Reasoning model (Evon or alternatives)

* We found **no public hosted Evon API endpoint** in the official docs. Gnani publishes the open weights `gnani/gnani-evon-v3.3-30B-A3B` on Hugging Face, with instructions to serve them via vLLM or SGLang (both give an OpenAI-compatible `/v1/chat/completions` API). Because no hosted endpoint was documented, none is hard-coded.
* The reasoning layer therefore accepts **any OpenAI-compatible server**:
  ```
  LLM_BASE_URL=http://localhost:8000/v1
  LLM_MODEL=gnani-evon-v3.3          # the name you passed to --served-model-name
  LLM_API_KEY=                        # only if your server needs one
  LLM_LABEL=Gnani Evon
  LLM_DISABLE_THINKING=true           # skips reasoning traces for faster voice replies
  ```
  Evon needs a large GPU to self-host. If you do not have one, point these variables at any other OpenAI-compatible provider you are allowed to use.
* With nothing configured, the app answers from the demo FAQ and says so. Every reply carries a label: **AI answer**, **Demo FAQ answer** or **Fallback message**, so FAQ text is never presented as live AI.

## 4. Verify your setup

```
pytest                                   # offline mocked tests
pytest tests/test_live_integration.py -v -s   # LIVE tests against real Gnani (needs your key)
```
Then open the app. The pill in the top bar turns to **All working** only after real Prisma and Timbre calls have succeeded.

## 5. Rate limits and errors
Some Gnani accounts allow only one active request at a time (HTTP 429). The backend retries once automatically and shows a friendly message otherwise. Mapped errors: 401 invalid/missing key, 402 no credits, 403 scope/credits, 429 rate limit, 400/422 bad request, 504 timeout, 5xx service unavailable.
