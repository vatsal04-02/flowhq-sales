# FlowHQ Outreach OS — Implementation Plan (low-cost edition)

Status (2026-10-26): M0–M7 core workflow implemented and tested against a mock email provider; see TASKS.md for the exact verified / not-verified list.
Implemented differently from the first plan: personalization is **template-first** (model only proposes a subject + opening line that must quote verified evidence), research is **model-free**, and replies are classified by **rules first** (a model only refines "unclear"; opt-outs are never left to a model). This is what makes a small, fast local model (or none at all) workable.
Not implemented: IMAP/real reply sync, SMTP exercised against a server, real Ollama runs, Docker/CI runs, M8 hardening.

## 1. Repository & environment assessment

| Item | Finding |
|---|---|
| Repo | Empty `/home/user`, not a git repo. Greenfield. Nothing to verify or reuse. |
| Runtimes | Python 3.13, Node 22 / npm 10, Docker 29, git 2.43 |
| Services on box | PostgreSQL 16 client, Redis 7 server binary |
| Hardware | 4 vCPU, 15 GB RAM, **no GPU**, ~30 GB free disk |
| Ollama | **Not installed.** No GPU means Qwen3:4b would run on CPU, at a few tokens/sec. |
| Outbound | Via proxy. Real SMTP/IMAP/provider calls cannot be tested from this sandbox, so mock + local Mailpit only. |

Consequences: the dev loop uses mock adapters and a local SMTP sink. "Real email works" can only be proven on the operator's machine/VPS with their credentials, so that item is marked **operator-verified** in the DoD.

## 2. Limitations (honest list)

**Legal / compliance (cannot be coded away)**
- A scraped email is not consent. B2B cold email is lawful in some places (e.g. CAN-SPAM opt-out model) and restricted in others (GDPR/PECR, CASL, India DPDP). The tool stores source, lawful-basis note, region, and enforces opt-out. The operator remains responsible for lawfulness. Per-lead `region` + campaign rule "block regions: X" is included.
- A phone number does not grant WhatsApp permission. WhatsApp is out of MVP.

**Platform**
- LinkedIn and Instagram have no compliant cold-DM API for this use case. They are **manual-assist only**: copy-ready drafts plus a "mark as sent" button. No automation, ever.
- WhatsApp requires Business verification, templates, and opt-in. Deferred to post-MVP.
- Gmail/Workspace send caps (~500/day consumer, ~2,000/day Workspace) and deliverability reputation limit volume. Default cap: **30/day per mailbox**, ramped up (warm-up schedule). We do not promise inbox placement.
- Google OAuth for sending needs app verification (slow, sometimes paid security review). **MVP uses SMTP + IMAP with app passwords**, so no OAuth review.

**AI**
- Qwen3:4b on CPU: slow (a single research summary may take minutes), weak at faithful extraction, and prone to inventing facts. It is kept as an optional adapter, **not the default**.
- LLMs cannot guarantee zero fabrication. Mitigation is structural: every factual claim in a draft must cite an evidence ID, a validator checks the quote exists in the stored page text, and unverifiable claims block approval.
- Research from websites only: JS-rendered sites, bot-blocked sites, and thin sites will yield "insufficient evidence", which routes to a conservative template or manual review. Expected: a meaningful share of leads (to be measured, not guessed).

**Scope honesty**
- Multi-tenant RLS, billing, SaaS admin, WhatsApp/LinkedIn/IG automation, auto-replies: out of the first build.
- No scale claims. 10k-row import is a test target, not a promise until measured.

## 3. Low-cost decisions (differences from PRD stack)

| PRD says | We do | Why / cost effect |
|---|---|---|
| Celery + Redis | **Postgres job queue** (`SELECT … FOR UPDATE SKIP LOCKED`) with one worker process and a scheduler loop | Removes a service and a dependency. Durable by construction, and jobs are visible in SQL. Redis added later only if measured necessary. |
| 6+ services | **4 containers**: `web`, `api`, `worker` (includes scheduler), `postgres` (+ `mailpit` in dev only) | Fits a ~$5–10/mo VPS. |
| Ollama default | **Pluggable LLM, default = local Ollama** (per operator decision 2026-10-26). Zero per-token cost; the trade-off is speed and quality. Mitigations: batch/overnight processing, small schema-constrained outputs, deterministic extraction first, **templated drafts with LLM filling only evidence-bound slots**, stricter validator, mandatory human approval. | Ollama is not installed in the dev sandbox (installer blocked, no GPU). Run it on the operator's machine/VPS; benchmark before relying on it. |
| LLM for research | **Deterministic extraction first** (fetch, clean text, meta tags, nav/services keywords, regex), LLM only to summarize cleaned text into schema-validated findings | Cuts tokens ~70–90%. |
| Postgres RLS | `workspace_id` on every tenant table, enforced in a repository layer + tests; RLS added when 2nd tenant appears | Single-agency MVP. Schema stays RLS-ready. |
| OAuth email | SMTP send + IMAP poll (app password, encrypted with Fernet key from env) | No Google verification, no per-message fees. |
| Next.js + Recharts | Keep Next.js + Tailwind, minimal Recharts (5 charts max), shadcn-style components | Free, OK on same VPS. |
| Hosted services | None required. Optional: Amazon SES SMTP for sending (very cheap), Mailgun/Resend webhooks later | |

**Estimated running cost (to verify against current prices before committing):**
- Hosting: one small VPS, ~$5–15/mo.
- Sending mailbox: existing Google Workspace/Zoho seat or SES; ~$0–6/mo per mailbox.
- LLM: local, so $0 per token; cost is CPU/RAM time. On CPU-only hardware expect several tokens/sec for a 4B model, so ~3–4k tokens in / ~0.6k out per lead is minutes per lead, run async in batches. A GPU box or a 16 GB+ RAM VPS is the practical requirement. Per-job time caps and `AIUsageRecord` (tokens, latency) are kept.
- Domain + DNS: ~$10–15/yr. Use a **separate sending domain**, never the main one.
- Total pilot: roughly **$10–30/mo** (more if you rent a GPU/large-RAM VPS for the model).

## 4. Missing decisions and defaults (override any)

| # | Decision | Default |
|---|---|---|
| D1 | Hosting target | Single VPS + Docker Compose + Caddy (auto-HTTPS) |
| D2 | LLM provider | **Local/open-source via Ollama (OpenAI-compatible endpoint)**; operator-chosen model, default `qwen3:4b` (extraction/classification) with optional larger model for drafting. Hosted APIs are not used. `fake` adapter for tests |
| D3 | Email transport | SMTP (send) + IMAP (replies); Mailpit in dev |
| D4 | Auth | Email+password (argon2), HttpOnly session cookie, roles: owner/admin/rep |
| D5 | Sending domain | Operator supplies; we ship SPF/DKIM/DMARC checklist + DNS checker |
| D6 | Jurisdictions | Region field per lead; default policy blocks EU/UK/CA sends unless operator records a lawful basis |
| D7 | Unsubscribe | One-click `List-Unsubscribe` header + footer link to public signed URL; plus reply-text "unsubscribe" detection |
| D8 | Physical address in footer | Required campaign setting (CAN-SPAM). Send blocked if empty |
| D9 | Dedup rule | Auto-merge only on exact normalized email, or exact (normalized phone), or exact profile URL. Domain+company match = *suggested*, needs human confirmation |
| D10 | Research fetch policy | Respect robots.txt, 1 req/sec/host, max 6 pages/site, 1 MB/page, 10s timeout, public IPs only |
| D11 | Approval | Always manual in MVP. "Auto-approve" does not exist yet |
| D12 | Default scoring | Rule-based weights per ICP criterion with unknown ≠ fail. LLM only extracts attributes; the score is computed deterministically |

## 5. Milestones

Each milestone: deployable, tests green, TASKS.md updated.

**M0 — Skeleton (Phase 0).** Repo, git, Docker Compose, FastAPI app, Alembic, Next.js shell, CI (lint+test), `/healthz`, structured JSON logging with redaction, ADR-001. *Accept:* `docker compose up` yields API health OK, migrated DB, web page loads; `pytest` and `npm test` pass.

**M1 — Auth + workspace + leads core.** Users/roles, workspace-scoped repository base, Lead/Company/ActivityLog/AuditLog, lead list with search/filter/pagination. *Accept:* cross-workspace access test fails closed.

**M2 — CSV import (Phase 1).** Upload (size/row limits), preview, column mapping, normalization (email/phone/URL/domain), formula-injection-safe error CSV, chunked worker job, progress, idempotent retry of failed rows, dedup per D9. *Accept:* 10k-row fixture imports without blocking API; re-import creates no duplicates; malformed/quoted/UTF-8 fixtures pass.

**M3 — Job queue + suppression foundation.** Postgres queue, retries/backoff, dead-letter view, SuppressionRecord keyed on normalized email/domain (survives re-import). *Accept:* kill-worker-mid-job test leaves no lost or duplicated work.

*(Review checkpoint: M0–M3 = requested Phase 0 + 1.)*

**M4 — Research + qualification.** SSRF-safe fetcher, extractor, evidence store, LLM adapter + fake, ICP profile, deterministic scorer with per-criterion breakdown. *Accept:* every finding has URL + excerpt + timestamp; unknown stays unknown; prompt-injection fixture page is ignored.

**M5 — Personalization + approval.** Structured generation, claim→evidence validator, versions, edit, approve/reject, policy gate. *Accept:* unapproved/unsupported-claim drafts cannot reach send queue.

**M6 — Email execution.** SMTP adapter + mock adapter, scheduled actions, idempotency keys, pre-send recheck, limits, unsubscribe endpoint, IMAP reply sync, threading, bounce→suppression, pause/kill switch. *Accept:* all safety acceptance tests from PRD §14 pass against Mailpit + mock; one real-mailbox pilot run by operator.

**M7 — Dashboard, inbox, pipeline, tasks.** Metrics with stated denominators, reply classification (suggestions only), Kanban, failed-job view, audit log UI.

**M8 — Hardening.** Backups/restore drill, load test numbers, security review, docs.

Later: SES/other providers, WhatsApp, manual-assist LinkedIn/IG workflow (small, can come earlier at low cost), RLS, billing.

## 6. Top risks

1. **Legal exposure from cold email** → region gating, lawful-basis field, mandatory unsubscribe + address, kill switch, audit log.
2. **Domain reputation burn** → separate domain, warm-up ramp, hard daily caps, auto-pause on bounce rate >2–3% or complaint signal.
3. **Hallucinated personalization** → evidence-ID citation + quote-substring validator + human approval.
4. **Duplicate sends** → idempotency key unique constraint, claim-then-send state machine, test with induced crashes.
5. **SSRF / prompt injection from scraped sites** → IP-range blocking after DNS resolution (and on redirects), content delimiters, schema-only outputs, no tools given to LLM.
6. **LLM cost drift** → per-job token caps, monthly budget hard stop, cache by content hash.
7. **IMAP fragility** (provider quirks, threading) → match on Message-ID/In-Reply-To/References then fallback sender+subject; unmatched replies go to a manual triage queue.
8. **Scope creep** → channels beyond email are separate milestones, each with own acceptance gate.

## 7. Test plan (initial)

- **Unit (pytest):** CSV parsing & normalization, dedup rules, ICP scoring, claim validator, state-transition table, sequence scheduling, suppression checks, metric formulas, idempotency keys.
- **Integration (pytest + real Postgres):** migrations up/down, queue claim/retry/crash recovery, webhook/IMAP ingestion with duplicate & out-of-order events, pause/resume, SMTP to Mailpit, workspace isolation.
- **Safety acceptance:** the 10 cases in PRD §14 each get a named test.
- **Frontend:** Vitest for components, Playwright for import→review→approve flow (Chromium is preinstalled).
- **E2E slice:** CSV → research (fixture site) → qualify → draft (fake LLM) → approve → send (Mailpit) → simulated reply → dashboard numbers match SQL.
- **LLM evals:** small golden set measuring fabricated-claim rate, schema-valid rate, latency, tokens/cost per lead. Benchmark Qwen3:4b only if the operator has suitable hardware.
- **Load (M8):** 10k import timing, dashboard query timings; report actual numbers.

## 8. Browser-agent for personal LinkedIn / Instagram — decision (2026-10-26)

Request: an agent that drives the operator's logged-in browser and sends DMs from personal LinkedIn/Instagram accounts with no API.

**Decision: not built.** Reasons:
1. The PRD (scope + FR-07) explicitly excludes unofficial automation of personal accounts and session/browser automation of these platforms.
2. LinkedIn and Instagram prohibit it in their terms and detect it. Practical result: restricted or permanently banned accounts, and for an agency selling its own services, losing the LinkedIn profile is a real business cost.
3. It is fragile (UI changes, CAPTCHAs, checkpoints) and would make the "approval-first, reliable" principle false for those channels.

**What we build instead (low cost, same workflow):** *Assisted manual channel* (`adapters/channels/manual.py`, `can_send=false`, `requires_manual_action=true`):
- Draft per lead per channel, short enough for the platform, evidence-linked, approval-gated like email.
- A "Work queue" page: one lead at a time, shows profile link (opens in a new tab in the user's own browser), a **Copy** button, and **Mark sent / Replied / Skip** buttons. The human pastes and presses send.
- Pacing guard: recommended daily cap and cooldown timer shown in the UI, reply/opt-out recorded manually, suppression applies.
- No scripts run inside LinkedIn/Instagram pages, no cookies/sessions handled by us.
- If the operator later gets official access (e.g. Instagram Messaging API on a professional account that the prospect has messaged first), it plugs in as a real adapter.
