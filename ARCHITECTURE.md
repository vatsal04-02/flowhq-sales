# FlowHQ Outreach OS — Architecture

Modular monolith. AI proposes; deterministic code decides and executes.

## 1. Runtime topology (dev and prod)

```
 Browser ─▶ Caddy (HTTPS) ─▶ web (Next.js)  ─▶ api (FastAPI /api/v1) ─▶ postgres
                                                  ▲                          ▲
                                       worker (job runner + scheduler) ──────┘
                                         │  ├─ research (httpx fetcher, SSRF guard)
                                         │  ├─ llm adapter (hosted | openai-compat/ollama | fake)
                                         │  └─ channel adapters (smtp/imap | mock | manual)
 dev only: mailpit (SMTP sink + UI)
```

- `api` never calls providers or LLMs inside request handlers. It enqueues jobs.
- `worker` claims jobs from Postgres (`FOR UPDATE SKIP LOCKED`), with lease expiry so crashed jobs are reclaimed.
- Redis is not in the MVP. Rate limits use a Postgres counter table. Add Redis only if measured.

## 2. Backend layering (`backend/app`)

```
api/        routers, request/response schemas, deps (auth, workspace)
domain/     pure logic, no I/O: state machines, scoring, dedup, policy gate,
            sequence scheduler, metrics, claim validator
services/   orchestration using repos + adapters (import, research, qualify,
            generate, approve, send, ingest_reply)
repos/      workspace-scoped DB access (the ONLY place queries are built)
adapters/
  llm/      base.py, anthropic.py, openai_compat.py, fake.py
  channels/ base.py (capabilities), smtp_imap.py, mock.py, manual.py
  fetch/    safe_fetcher.py (SSRF guard, robots, limits)
jobs/       queue.py, runner.py, handlers/, scheduler.py
models/     SQLAlchemy models
core/       config (env), security (argon2, fernet), logging (redaction), errors
```

Rules enforced by tests: `domain/` imports nothing from `adapters/`, `repos/`, or `api/`. Routers do not touch the ORM directly.

## 3. Channel adapter contract

```python
class ChannelCapabilities(BaseModel):
    can_send: bool; can_receive: bool; syncs_delivery: bool
    can_draft: bool; supports_templates: bool; requires_manual_action: bool
    required_permissions: list[str]; rate_limit: RateLimit | None

class ChannelAdapter(Protocol):
    capabilities: ChannelCapabilities
    def send(self, msg: OutboundMessage, idempotency_key: str) -> SendResult: ...
    def poll_events(self, since: Cursor) -> list[ProviderEventIn]: ...
    def health(self) -> Health: ...
```

The send service refuses to call `send` if `can_send` is false. `mock` adapter results carry `simulated=true` and are never counted as real "sent" in analytics (separate flag shown in the UI).

## 4. Send safety pipeline (single code path)

`ScheduledAction(due)` → claim (state `due→claiming`, lease) → **policy gate** recheck: message approved & unedited since approval (hash), lead not suppressed/opted-out/replied/bounced, campaign active, kill switch off, channel can_send, region rule, quiet hours, per-mailbox daily/hourly limit → insert `Message(state=sending)` keyed by unique `idempotency_key` → adapter.send → record provider ID, state `sent` → create next step action. On crash after provider accepted but before recording, the retry finds the existing key and **reconciles via sent-folder/Message-ID lookup instead of re-sending**; if it cannot reconcile, it marks `needs_manual_check` rather than risking a duplicate.

## 5. State machines (explicit tables in `domain/states.py`)

- Lead outreach status: imported → needs_research → qualified|unqualified → ready_for_review → approved → active_outreach → replied|bounced|unsubscribed|suppressed … Transitions are a whitelist and every change writes ActivityLog. AI code has no write access to status.
- Opportunity stage is a separate field.
- ScheduledAction: pending → due → claiming → sent | failed(retry n) | cancelled | needs_manual_check.

## 6. Data model (UUID PKs; all tenant tables have `workspace_id`, `created_at`, `updated_at`; soft-delete `deleted_at` on leads/companies/campaigns)

| Entity | Key fields / constraints |
|---|---|
| Workspace, User, Membership(role) | unique(workspace,user) |
| Company | domain (normalized), name, location; unique(workspace, domain) when domain present |
| Lead | company_id, names, title, email_norm, phone_e164, linkedin_url, instagram_url, region, custom JSONB, raw JSONB (original CSV values), source_url, collected_at, lawful_basis, status, owner_id; unique(workspace, email_norm) partial where not null |
| ImportBatch / ImportRowError | file hash, mapping JSONB, counters, row number, reason, raw row |
| ResearchJob / ResearchEvidence | url, excerpt, retrieved_at, confidence, kind(`verified`/`inferred`), content_hash; refresh_after |
| ICPProfile | criteria JSONB (weights, rules), thresholds |
| Campaign / CampaignSequenceStep / CampaignLead | unique(campaign, lead); channel list, limits, schedule, tz, footer address, stop rules |
| GeneratedMessage / MessageApproval | version, body, subject, evidence_ids[], validator_report JSONB, content_hash, approved_by, approved_hash |
| ChannelAccount | provider, encrypted_credentials (Fernet), capabilities, health, daily_limit |
| Conversation / Message | thread keys (Message-ID, References), direction, simulated flag, idempotency_key UNIQUE |
| ProviderEvent | unique(provider, external_event_id) for dedup/replay; payload; processed_at |
| ScheduledAction | lead, campaign, step, channel, run_at, state, retry_count, idempotency_key UNIQUE, last_error, lease_until |
| Job | generic queue row: type, payload, state, attempts, run_after, lease_until, last_error |
| SuppressionRecord | workspace, kind(email/domain/phone), value_norm, reason, source; unique; **never deleted by lead edits/reimports** |
| Task, Opportunity, ActivityLog, AuditLog (append-only), AIUsageRecord (tokens, cost, latency, model, job) | |

## 7. API contract (`/api/v1`, JSON, cursor pagination `?cursor=&limit=`, errors `{error:{code,message,details}}`)

MVP-first surface (the PRD list is kept; additions marked +):

- Auth: `POST /auth/login`, `POST /auth/logout`, `GET /me`
- Imports: `POST /imports` (upload, returns preview), `PUT /imports/{id}/mapping`, `POST /imports/{id}/start`, `GET /imports/{id}` (progress), `GET /imports/{id}/errors.csv`, `POST /imports/{id}/retry-failed` (+)
- Leads: `GET /leads`, `GET /leads/{id}`, `PATCH /leads/{id}`, `POST /leads/{id}/research`, `POST /leads/{id}/qualify`, `GET /duplicates` + `POST /duplicates/{id}/merge` (+)
- Campaigns: as in PRD plus `POST /campaigns/{id}/kill`; global `POST /workspace/kill-switch` (+)
- Messages: list/get/edit/approve/reject; `POST /messages/{id}/send` only enqueues a ScheduledAction through the policy gate.
- Inbox, Opportunities, Analytics (each metric returns `{value, numerator, denominator, window}`), Integrations, Jobs (`GET /jobs?state=failed`, `POST /jobs/{id}/retry`) (+)
- Public: `GET/POST /u/{signed_token}` unsubscribe (no auth, signed + expiring), `POST /webhooks/{provider}` (signature verified).
- OpenAPI served at `/api/v1/openapi.json`.

## 8. Folder structure

```
/home/user
├── PRD.md  ARCHITECTURE.md  IMPLEMENTATION_PLAN.md  TASKS.md  CLAUDE.md  README.md
├── docs/adr/0001-modular-monolith-postgres-queue.md
├── docker-compose.yml  docker-compose.prod.yml  Caddyfile  .env.example
├── backend/
│   ├── pyproject.toml  alembic.ini  migrations/
│   ├── app/{api,domain,services,repos,adapters,jobs,models,core}/
│   └── tests/{unit,integration,safety,fixtures}/
├── frontend/   (Next.js app router, Tailwind, src/{app,components,lib})
└── .github/workflows/ci.yml
```

## 9. Security essentials

Argon2 passwords; HttpOnly+SameSite cookies, CSRF token on mutating calls; credentials Fernet-encrypted with key from env, never returned by API; log redaction filter; upload limits (size, rows, MIME); CSV export prefixes `= + - @` cells; fetcher resolves DNS and blocks private/link-local/metadata ranges, re-checks on every redirect; LLM prompts wrap untrusted text in delimiters, models get no tools, outputs schema-validated; HTML never rendered raw (text only/sanitized).
