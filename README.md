# BhashaBridge AI

**Breaking Language Barriers Through Voice Intelligence.**

BhashaBridge AI is a multilingual voice assistant for Indian students. Speak in English, Hindi, Kannada, Tamil or Telugu; the app transcribes your speech, writes a helpful answer, and speaks it back.

Built for the **Great Indian AI Internship Challenge** by Gnani AI. Speech recognition uses **Gnani Prisma** and voice output uses **Gnani Timbre**. Thank you to Gnani.ai for the APIs and documentation. This is an independent project, not endorsed by Gnani.ai.

## Status: please read
* The code follows the official Gnani docs (endpoints, headers, fields, voices, error formats were checked against docs.gnani.ai).
* Mocked tests and a mock-server browser test pass. **Live calls to the real Gnani API have not been run yet**, because the build environment had no network route to Gnani and no key. Run `pytest tests/test_live_integration.py -v -s` with your key to prove it on your machine (see `docs/TESTING_REPORT.md`).
* **Evon:** no public hosted endpoint was found in the official docs, so none is faked. The reasoning layer accepts any OpenAI-compatible server (for example self-hosted Gnani Evon), with a labelled demo-FAQ fallback.

## Quick start (Windows)
1. Install **Python 3.10+** from python.org (tick *Add python.exe to PATH*).
2. Extract the ZIP and open the folder in **VS Code**.
3. Open a terminal (Ctrl + backtick) and run: `run.bat`
4. On first run it creates `.env` and opens Notepad. Replace `your_new_api_key` with your Gnani key (from <https://app.gnani.ai/>), save, then run `run.bat` again.
5. The browser opens at <http://127.0.0.1:5000>. Allow microphone access when asked.

Linux / macOS: `./run.sh`.

Manual setup:
```
python -m venv venv
venv\Scripts\activate          # macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
copy .env.example .env         # macOS/Linux: cp .env.example .env   (then edit .env)
python app.py
```

## Using it
* **Assistant** (`/dashboard`): choose a language, tap the mic, speak, tap again to stop. Or type. Replay or copy any answer.
* **Student help** (`/student`): search FAQs by category, or ask the assistant. FAQ content is **demonstration data**: edit `database/faq_data.json` with your institution's verified information.
* The pill in the top bar shows API status. It says **All working** only after real calls succeeded.

## Optional: add a reasoning model
Edit `.env` (see `docs/API_SETUP.md`):
```
LLM_BASE_URL=http://localhost:8000/v1
LLM_MODEL=gnani-evon-v3.3
LLM_LABEL=Gnani Evon
```
Without it, answers come from the demo FAQ and are labelled as such.

## Tests
```
pytest                                          # offline mocked tests (57)
pytest tests/test_live_integration.py -v -s     # LIVE Gnani tests (needs GNANI_API_KEY)
```

## Documentation
* `docs/API_SETUP.md`: key setup, endpoints, voices, Evon/LLM options
* `docs/PROJECT_ARCHITECTURE.md`: design and data flow
* `docs/TESTING_REPORT.md`: what was and was not verified
* `docs/DEMO_SCRIPT.md`: 60-second demo script
* `docs/LINKEDIN_POST.md`: post draft

## Troubleshooting
| Problem | Fix |
|---|---|
| `python` not recognised | Reinstall Python and tick *Add to PATH*, or use `py -3` |
| Status pill says **Add API key** | Set `GNANI_API_KEY` in `.env` and restart the app |
| "Gnani rejected the API key" | Key typo, revoked, or no access to the speech service: check the dashboard |
| "insufficient credits" / 403 | Add credits or confirm your key has STT and TTS access |
| Mic does nothing / "permission denied" | Click the lock icon in the address bar → allow microphone. Use `http://127.0.0.1:5000` or `localhost`, not a LAN IP |
| "Could not hear any speech" | Speak closer, 2 to 20 seconds, pick the right language first |
| "rate limiting" (429) | Wait a few seconds; some accounts allow one request at a time |
| Reply not spoken | Tick *Speak replies aloud*, or press **Play** (browsers can block autoplay) |
| Port 5000 busy (macOS AirPlay) | Set `PORT=5050` in `.env` |
| Fonts look plain offline | Cosmetic: Google Fonts need internet; the app still works |

## Privacy
Voice clips are processed in memory and forwarded to Gnani; this app never saves them. Chat text is stored in a local SQLite file (`instance/`) and can be deleted with **Clear**. The API key lives only in `.env` on the server. Never commit `.env`.

## Project structure
See `docs/PROJECT_ARCHITECTURE.md`. Main entry point: `app.py`.

## Team
Solo project. Update the About page (`templates/about.html`) with your name and college.
