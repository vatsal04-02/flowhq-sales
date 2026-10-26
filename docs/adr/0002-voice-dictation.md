# ADR-0002: Voice dictation: queued transcription behind a replaceable speech adapter

Status: accepted (2026-10-27)

**Context.** Users want to dictate into campaign forms, draft/reply composers and notes, in English, Hindi and
Hinglish. Project rules: handlers never call models inline; every AI call goes through a provider-independent
interface; no new services without an ADR; dictation must never trigger a send.

**Decision.**
- *Queued, not inline.* `POST /voice/transcriptions` validates and stores the upload, enqueues a `voice_transcribe`
  job (Postgres queue, ADR-0001) and returns 202. The worker transcribes; the browser polls `GET /voice/transcriptions/{id}`.
- *Replaceable speech adapter.* `adapters/stt` defines `SpeechToText`. Providers: `none` (default: feature off),
  `fake` (tests), `openai_compat` (any server exposing `POST {base}/audio/transcriptions`: a local Whisper-compatible
  server, or an authorised hosted provider). No Whisper container is added to `docker-compose.yml`; the operator
  points `STT_BASE_URL` at one. "Local" vs "cloud" is inferred from the URL (overridable) and shown to users.
- *Audio lifetime.* Audio exists only in `voice_transcription.audio` between upload and processing and is set to NULL in a
  `finally` (success, failure, crash). A housekeeping pass wipes any stray blob older than 15 minutes and deletes
  rows after `VOICE_RETENTION_HOURS`. Audio and transcripts are never logged.
- *Transcript is the source of truth.* Cleanup is a separate, optional step through `call_llm` (untrusted-data delimiters, JSON
  schema, usage recorded). `domain/voice.check_cleanup` accepts it only if every number, amount, URL, email, month/day word and
  mid-sentence name is unchanged and the edit is light; otherwise the raw transcript is returned with a note.
- *No path to sending.* Dictation produces text that the browser inserts into a field after the user reviews it. The voice code
  imports nothing from the send service, and a safety test asserts no message, schedule or draft is ever created by it.
- *Limits.* Per-user hourly cap (cancelled dictations still count), size/duration caps, format sniffed from magic bytes
  (the client Content-Type is ignored), authenticated and CSRF-protected like every other mutation.

**Alternatives rejected.** Browser Web Speech API (audio goes to a vendor's cloud, no control over Hindi/Hinglish quality, not
replaceable); synchronous transcription in the request handler (breaks the no-inline-model rule and ties up API workers); a
bundled Whisper service in compose (a new service to operate; can be added later behind this same interface).

**Consequences.** Adds roughly the worker poll interval (about 1-2 s) to each dictation. Audio briefly lives in Postgres as `bytea`;
deleting it does not erase it from WAL, dead tuples or backups until those age out. Speech quality is entirely the chosen model's:
Hindi and Hinglish need a larger model than English and must be measured with `scripts/bench_stt.py` on real recordings.
