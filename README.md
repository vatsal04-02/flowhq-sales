# FlowHQ Outreach OS

Approval-first outreach platform. Planning docs: `PRD.md`, `ARCHITECTURE.md`, `IMPLEMENTATION_PLAN.md`, `TASKS.md`.
Current state: milestones M0–M3 (see TASKS.md for what is and is not verified).

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
