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

## M4 Research & qualification — DONE (tested with fixture site)
- [x] SSRF-guarded fetcher (public IPs only, re-checked per redirect, port/scheme limits, size/time caps), robots.txt respected
- [x] Deterministic extraction -> verbatim evidence with URL, excerpt, timestamp, confidence, kind; 30-day cache
- [x] Configurable ICP scoring with per-criterion breakdown; unknown excluded from score, lowers confidence; exclusions; thresholds
- [x] Insufficient research -> no drafts by default, optional conservative draft flagged for manual review
- [ ] Research uses no LLM by design (fast, cheap). "Inferred" evidence kind exists but nothing writes it yet.

## M5 Personalization & approval — DONE (tested with fake LLM + templates)
- [x] LLM interface (Ollama/OpenAI-compatible, fake, none); schema-validated; usage/latency/failures recorded
- [x] Template-first drafts; model may only propose subject+opening, which must cite verified evidence with an exact quote; otherwise rejected -> template
- [x] Validator: banned phrases, unverified numbers, placeholders, length per channel; spammy/instruction-like site text is never quoted
- [x] Edit invalidates approval (hash); errors block approval; bulk "approve all clean"
- [ ] **Never run against a real model.** Prompts/JSON compliance of qwen2.5 are unverified; use `python -m scripts.bench_llm`.

## M6 Email execution — DONE for mock provider; SMTP adapter written, not exercised
- [x] Policy gate (kill switch, approval hash, campaign state, suppression, region, address, limits, working hours, replied/stopped)
- [x] Idempotent send: intent recorded before provider call; crash -> needs_manual_check, never silently resent; retries with backoff
- [x] Sequence scheduling, in-thread follow-ups, pause/resume (held not lost), daily limits defer
- [x] Unsubscribe link + RFC 8058 header; GET never unsubscribes; reply opt-out is rule-based; bounce -> suppression
- [x] Inbound matching by In-Reply-To then sender; duplicate events ignored; intent rules + optional model for "unclear"; human reclassify
- [ ] **IMAP/real reply sync NOT built.** Only sandbox-simulated replies/bounces exist.
- [ ] SMTP adapter never tested against a real or local SMTP server.
- [ ] No delivery/bounce webhooks from real providers.

## M7 Dashboard, inbox, pipeline — DONE (browser-tested)
- [x] Dashboard with numerators/denominators/windows; real vs simulated vs manual sends separated
- [x] Inbox with thread, intent editing, suggested replies, human reply (through suppression checks), sandbox tools
- [x] Kanban with drag + menu; opportunity auto-created on positive reply; stage mirrors to lead status where allowed
- [x] Manual queue for LinkedIn/Instagram (copy, open profile, mark sent). No automation.
- [x] Failed/held sends, jobs, audit log views
- [x] Time-series chart (sent / replies / positive per day, hover values, direct labels + dash styles so colour is not the only signal), sparklines, rate rings, funnel with stage conversion %, ICP donut
- [x] UI polish pass: dark sidebar shell, branded login, avatars, depth/shadows, responsive charts (no overflow at 375px), campaign page auto-refresh after actions
- [ ] No Task entity (upcoming sends and manual queue stand in); no user/role management UI, data export/deletion, retention, webhook config
- [ ] No login rate limiting; no Postgres RLS; no assignment of leads/conversations

## Declined by design
- Browser agent that logs in to personal LinkedIn/Instagram and sends DMs: not built (platform terms, account-ban risk, PRD exclusion). Manual-assist queue instead.

## Verification (latest)
- 73 backend tests (unit, integration, safety incl. 10k-row import), ruff clean; /analytics/timeseries covered
- tsc clean, `next build` OK
- Playwright journey (login → import → campaign → research → score → drafts → approve → launch → simulated reply → dashboard → pipeline), 375px no horizontal overflow, no console errors
- NOT verified: Docker compose, GitHub CI, real SMTP, real Ollama, real IMAP

## M8 Hardening — NOT STARTED (load tests, backup/restore drill, security review, deploy automation)
