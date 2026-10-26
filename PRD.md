# FlowHQ Outreach OS — PRD (working copy)

The full PRD v1.0 was provided in the project request. This file records the product intent and the **amendments agreed for the low-cost build**. Technical detail lives in ARCHITECTURE.md and IMPLEMENTATION_PLAN.md.

## Goal
Turn an imported lead CSV into a researched, qualified, personalized, approval-gated, measurable email outreach pipeline for a single agency workspace, with a path to multi-tenancy.

## Principle
AI generates and reasons about content. Deterministic software controls execution, scheduling, permissions, retries, and state.

## MVP scope
CSV import/mapping/dedup · lead management · website research with evidence · ICP scoring · personalized drafts with evidence citations · campaigns & sequences · approval queue · email send (SMTP) + reply sync (IMAP) · suppression/unsubscribe/kill switch · inbox · dashboard with defined metrics · basic pipeline · job/failure visibility · audit log.

## Out of scope (first release)
Lead scraping/buying · mass multi-channel blasting · unofficial platform automation · autonomous replies · general browser agent · billing/multi-tenant admin · WhatsApp, LinkedIn, Instagram automation (LinkedIn/IG: manual-assist drafts only).

## Amendments for low cost
1. Postgres-backed job queue replaces Celery/Redis; 4 containers total.
2. SMTP+IMAP replaces OAuth providers in MVP.
3. Default LLM is a small hosted model with a hard budget cap; local Ollama/Qwen3:4b is optional (no GPU in dev environment).
4. Deterministic extraction precedes LLM summarization to cut tokens.
5. Workspace scoping in repo layer now; Postgres RLS when a second tenant exists.
6. Target running cost: roughly $10–30/month for a pilot (to be verified).

## Definition of Done
As in the original PRD §16, with "real email works" verified by the operator on their own mailbox, and all safety acceptance tests (original §14) passing automatically.
