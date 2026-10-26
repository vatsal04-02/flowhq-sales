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
5. **Reply detection (IMAP).** In Integrations → Add SMTP, also fill the IMAP section (e.g. Gmail/Workspace: `imap.gmail.com`, port 993, SSL, an *app password*; IMAP must be enabled in the mailbox settings). FlowHQ then checks the INBOX about once a minute (or press "Check mailbox now"):
   - it is **read-only**: mail is opened with EXAMINE and BODY.PEEK, so nothing is marked as read, moved or deleted;
   - replies are matched by `In-Reply-To`/`References`, then by sender; mail that matches no lead is listed in the Inbox ("could not be matched") and changes nothing;
   - opt-outs ("unsubscribe", "remove me") suppress immediately; out-of-office auto-replies are recognised from headers and never stop the sequence or count as replies;
   - permanent bounces (5.x.x) suppress the address and stop follow-ups; temporary ones (4.x.x) are only logged; unclear bounce notices pause the sequence without suppressing;
   - the first check only looks at the last 7 days, then follows a UID cursor; a mailbox that cannot be reached is shown on the Integrations page and the dashboard, and nothing is lost while it is down.
   Not covered: replies filed into Spam or other folders (only INBOX is read), OAuth-only mailboxes (use an app password), threads that lose their `In-Reply-To` header and come from a different address than the lead's.
