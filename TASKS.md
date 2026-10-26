# TASKS

Legend: [ ] todo · [~] in progress · [x] done AND acceptance tested. Update after every milestone.

## Planning
- [x] Repository/environment assessment (empty repo; Py3.13, Node22, Docker, PG16, Redis7; no GPU, no Ollama)
- [x] IMPLEMENTATION_PLAN.md, ARCHITECTURE.md, TASKS.md, CLAUDE.md, PRD.md
- [x] Operator decisions: local/open-source LLM (Ollama); no browser automation of personal LinkedIn/Instagram (manual-assist instead, IMPLEMENTATION_PLAN §8)

## M0 Skeleton — DONE except Docker verification
- [x] .gitignore, .env.example (no secrets); git init done (no commits yet)
- [x] FastAPI app + /healthz, env config
- [x] Alembic baseline; downgrade base -> upgrade head runs at the start of every test session
- [x] JSON logging with secret/email redaction (unit tested)
- [x] Next.js shell on design-system tokens (design-system/flowhq-outreach-os/MASTER.md)
- [x] CI workflow written (ruff, pytest, tsc, next build) — not yet run on GitHub
- [x] ADR-0001
- [ ] docker-compose / Dockerfiles written but **NOT verified**: sandbox has no Docker daemon. Operator must run `docker compose up --build`.

## M1 Auth, workspace, leads core — DONE
- [x] User/Workspace/Membership, argon2 login, signed HttpOnly cookie, CSRF header, CLI create-admin
- [x] Workspace-scoped repos; cross-workspace tests (leads, imports, errors.csv, start) all return 404
- [x] Lead/Company models; keyset pagination, search, status/region filters; lead detail + timeline
- [x] ActivityLog + AuditLog (suppression, status changes, imports)
- [ ] Role enforcement beyond suppression delete (rep/admin split barely used yet)
- [ ] Login rate limiting (not implemented)

## M2 CSV import — DONE
- [x] Limits (10 MB / 50k rows), UTF-8 + BOM, delimiter sniffing, quoted/multiline fields, blank lines
- [x] Mapping suggestion + UI + preview
- [x] Normalizers: email, phone E.164, website, LinkedIn /in/, Instagram, domain
- [x] Dedup: exact email > phone > linkedin > instagram; domain + last name is only *suggested*
- [x] Chunked worker import, progress, resume cursor, idempotent re-run
- [x] Formula-safe error report CSV; retry-failed rows
- [x] 10k rows: API returns immediately; worker took ~80 s on this 4-vCPU sandbox (~8 ms/row, not optimized)

## M3 Queue + suppression — DONE
- [x] Postgres queue: SKIP LOCKED claim, lease, backoff, dead state, manual retry
- [x] Lease-expiry/crash recovery tests
- [x] SuppressionRecord (email/domain/phone) enforced at import; survives lead deletion/re-import
- [x] Jobs + suppression UI

**Verification:** 34 backend tests (unit/integration/safety), ruff clean, tsc clean, `next build` OK, and an ad-hoc
Playwright run (login error, upload, map, import, leads, detail, jobs, 375px width) passed.
Not covered yet: committed frontend/Playwright tests, real Docker run, real SMTP/LLM.

## Later (M4–M8): see IMPLEMENTATION_PLAN.md §5

## Blockers / open items
- Real SMTP/IMAP and hosted-LLM calls cannot be tested in this sandbox; need operator credentials and a test mailbox.
