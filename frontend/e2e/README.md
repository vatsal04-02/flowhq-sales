# Browser journey

Drives the real UI: login → sandbox account → CSV import → campaign → research → score → drafts → approve → launch → simulated reply → dashboard/pipeline, plus a 375px overflow check.

1. Start Postgres, `uvicorn app.main:app`, `python -m app.jobs.runner` and `next start` with `ALLOW_PRIVATE_FETCH=true LLM_PROVIDER=none PUBLIC_BASE_URL=http://localhost:3000`.
2. `python -m app.cli create-admin e2e@example.com e2e-password-123`
3. Serve a fixture site: write `index.html`, `services.html`, `robots.txt` (see `backend/tests/helpers.py` HOME/SERVICES) and run `python -m http.server 8765 --bind 127.0.0.1`.
4. `NODE_PATH=$(npm root -g) node e2e/journey.js` (resets nothing: use a throwaway database).

# Voice dictation journey

`e2e/voice.js` drives dictation in real Chrome with a fake microphone that plays a generated tone: recording indicator, review step, insert without overwriting, cancel, clearing history, and a genuinely blocked microphone. It asserts behaviour, not words.

1. Same stack as above, but start the API and worker with `STT_PROVIDER=fake` (canned transcript, no speech model needed) or point `STT_PROVIDER=openai_compat` at a real speech server.
2. `NODE_PATH=$(npm root -g) E2E_EMAIL=e2e@example.com E2E_PASSWORD=e2e-password-123 node e2e/voice.js` (needs Google Chrome; set `E2E_CHANNEL=chromium` to use Playwright's own build).
