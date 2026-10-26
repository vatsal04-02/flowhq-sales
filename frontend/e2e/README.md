# Browser journey

Drives the real UI: login → sandbox account → CSV import → campaign → research → score → drafts → approve → launch → simulated reply → dashboard/pipeline, plus a 375px overflow check.

1. Start Postgres, `uvicorn app.main:app`, `python -m app.jobs.runner` and `next start` with `ALLOW_PRIVATE_FETCH=true LLM_PROVIDER=none PUBLIC_BASE_URL=http://localhost:3000`.
2. `python -m app.cli create-admin e2e@example.com e2e-password-123`
3. Serve a fixture site: write `index.html`, `services.html`, `robots.txt` (see `backend/tests/helpers.py` HOME/SERVICES) and run `python -m http.server 8765 --bind 127.0.0.1`.
4. `NODE_PATH=$(npm root -g) node e2e/journey.js` (resets nothing: use a throwaway database).
