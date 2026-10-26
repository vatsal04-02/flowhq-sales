# FlowHQ Outreach OS

Approval-first outreach platform. Planning docs: `PRD.md`, `ARCHITECTURE.md`, `IMPLEMENTATION_PLAN.md`, `TASKS.md`.
Current state: M0–M7 core workflow built and tested with a mock email provider (see TASKS.md for exactly what is and is not verified).

**Flow:** import CSV → add to campaign → research (public website, robots.txt respected) → ICP score (unknown ≠ fail) → evidence-cited drafts → you approve → worker sends through a policy gate → replies classified → dashboard/pipeline.
**LinkedIn/Instagram:** manual-assist only (copy draft, send yourself, mark sent). No browser automation of personal accounts, by design.

## Run locally (without Docker)
```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.lock pytest ruff
export DATABASE_URL=postgresql+psycopg://USER:PASS@localhost:5432/flowhq   # your own Postgres 16
.venv/bin/alembic upgrade head
.venv/bin/python -m app.cli create-admin you@example.com 'a-long-password' 'My Workspace'
.venv/bin/uvicorn app.main:app --port 8000        # API + docs at /api/v1/docs
.venv/bin/python -m app.jobs.runner               # worker (second terminal)
cd ../frontend && npm install && API_URL=http://localhost:8000 npm run dev
```
## Run with Docker
`cp .env.example .env`, edit the CHANGE values, `docker compose up --build`, then
`docker compose exec api python -m app.cli create-admin EMAIL PASSWORD`.

## Tests
`cd backend && .venv/bin/pytest -q` (needs a Postgres with database `flowhq_test`; see `tests/conftest.py`).

## Backups
`pg_dump -Fc flowhq > flowhq.dump` / `pg_restore -d flowhq --clean flowhq.dump`. A restore drill is a TODO for M8.

## Local model (optional, recommended for nicer opening lines)
```bash
ollama pull qwen2.5:3b-instruct          # or qwen2.5:1.5b-instruct for speed
export LLM_PROVIDER=ollama LLM_MODEL=qwen2.5:3b-instruct
cd backend && python -m scripts.bench_llm 3   # measures JSON validity, fabricated-claim rate, latency
```
With `LLM_PROVIDER=none` (default) drafts use deterministic evidence-based templates and need no model. If the model is down, the system falls back to templates automatically and records the failure.

## Before sending real email
1. Use a **separate sending domain** (not your main one) and set SPF, DKIM and DMARC for it at your DNS provider.
2. Add an SMTP account in Integrations (app password), start with 20–30/day and ramp slowly. Gmail/Workspace have hard daily caps.
3. Every campaign needs a physical postal address and gets a one-click unsubscribe link automatically.
4. Check your legal position per recipient region (CAN-SPAM, GDPR/PECR, CASL, India DPDP). EU/UK/CA regions are blocked by default.
5. Reply detection for real mailboxes (IMAP) is **not built yet**: until then, replies from real recipients must be handled in your mailbox. The sandbox simulates replies.
