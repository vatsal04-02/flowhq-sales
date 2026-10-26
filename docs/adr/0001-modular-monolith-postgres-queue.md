# ADR-0001: Modular monolith with a Postgres-backed job queue

Status: accepted (2026-10-26)

**Context.** Single-agency MVP on a low budget. Needs durable background jobs (imports, research,
sends) and an auditable source of truth.

**Decision.** FastAPI modular monolith + one worker process. Jobs live in Postgres and are claimed with
`FOR UPDATE SKIP LOCKED` plus a lease; handlers are idempotent (at-least-once). No Redis/Celery.

**Consequences.** One fewer service to run and secure; jobs are queryable and auditable in SQL; failed
jobs are visible and retryable. Throughput is bounded by Postgres (fine for thousands of jobs/hour).
Revisit with measurements if sends or research exceed that.
