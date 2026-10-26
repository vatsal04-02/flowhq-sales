"""Voice dictation pipeline: validate and queue an upload, transcribe it in the worker, optionally tidy the text.

Privacy rules enforced here: audio is stored only between upload and processing and is wiped whether processing
succeeds or fails; audio and transcripts are never written to application logs; nothing here can send a message."""
import logging
import time
import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.adapters.llm.base import LLMUnavailable, call_llm, get_llm
from app.adapters.stt.base import STTError, get_stt
from app.core.config import get_settings
from app.domain import voice as dv
from app.jobs import queue
from app.models import AIUsageRecord, Job, VoiceTranscription
from app.repos.voice import LIVE, VoiceRepo, purge_expired

log = logging.getLogger("voice")

MIN_AUDIO_BYTES = 800        # a recording with no audio in it is just a container header
MIN_DURATION_MS = 300
CLEANUP_MAX_CHARS = 2000     # longer dictations skip cleanup: the original is shown instead


class VoiceError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


class CleanOut(BaseModel):
    text: str = Field(max_length=5000)


def info(db: Session, workspace_id: uuid.UUID, user_id: uuid.UUID) -> dict:
    """What the browser may know about the voice setup. Never includes endpoints or credentials."""
    s, stt = get_settings(), get_stt()
    return {
        "enabled": stt is not None, "provider": stt.name if stt else None, "processing": stt.processing if stt else None,
        "cleanup_available": stt is not None and get_llm() is not None,
        "languages": [{"code": c, "label": label} for c, label in dv.LANGUAGES.items()],
        "max_seconds": s.voice_max_seconds, "max_bytes": s.voice_max_bytes, "retention_hours": s.voice_retention_hours,
        "history_count": VoiceRepo(db, workspace_id, user_id).history_count(),
    }


def submit(db: Session, workspace_id: uuid.UUID, user_id: uuid.UUID, data: bytes, language: str, cleanup: bool,
           duration_ms: int | None) -> VoiceTranscription:
    s = get_settings()
    if get_stt() is None:
        raise VoiceError(503, "voice_disabled", "Voice input is not set up on this server. Ask an admin to configure a speech service.")
    if language not in dv.LANGUAGES:
        raise VoiceError(422, "bad_language", f"language must be one of {', '.join(dv.LANGUAGES)}")
    if len(data) > s.voice_max_bytes:
        raise VoiceError(413, "too_large", f"Recording is too large (limit {s.voice_max_bytes // (1024 * 1024)} MB). Try a shorter one.")
    if duration_ms is not None and duration_ms > (s.voice_max_seconds + 5) * 1000:
        raise VoiceError(413, "too_long", f"Recording is longer than {s.voice_max_seconds} seconds.")
    if len(data) < MIN_AUDIO_BYTES or (duration_ms is not None and duration_ms < MIN_DURATION_MS):
        raise VoiceError(422, "empty_recording", "The recording was empty. Hold the microphone button and speak, then stop.")
    if dv.sniff_audio(data) is None:
        raise VoiceError(415, "unsupported_format", "This audio format is not supported. Use a current Chrome, Edge, Firefox or Safari.")
    repo = VoiceRepo(db, workspace_id, user_id)
    if repo.count_last_hour() >= s.voice_max_per_hour:
        raise VoiceError(429, "rate_limited", f"Dictation limit reached ({s.voice_max_per_hour} per hour). Try again later.")
    row = VoiceTranscription(workspace_id=workspace_id, user_id=user_id, status="queued", language=language,
                             cleanup_requested=cleanup, audio=data, audio_bytes=len(data), duration_ms=duration_ms)
    db.add(row)
    db.flush()
    queue.enqueue(db, "voice_transcribe", {"id": str(row.id)}, workspace_id, max_attempts=2)
    return row


def expire_if_stuck(row: VoiceTranscription) -> None:
    """A queued/processing row that outlives the provider timeout means the worker is down or crashed."""
    if row.status in LIVE and (datetime.now(timezone.utc) - row.created_at).total_seconds() > get_settings().stt_timeout_seconds + 90:
        row.status, row.audio, row.error_code = "failed", None, "timeout"
        row.error_message = "Transcription did not finish in time. Your text was not changed; try again."
        row.finished_at = datetime.now(timezone.utc)


def _fail(row: VoiceTranscription, code: str, message: str) -> None:
    row.status, row.error_code, row.error_message, row.audio = "failed", code, message[:300], None
    row.finished_at = datetime.now(timezone.utc)


def _cleanup(db: Session, workspace_id: uuid.UUID, raw: str) -> tuple[str | None, str | None]:
    """(cleaned text or None, note for the user). The raw transcript wins unless the cleanup provably kept every fact."""
    if len(raw) > CLEANUP_MAX_CHARS:
        return None, "Too long to tidy up, so this is the original."
    if get_llm() is None:
        return None, "Cleanup is not set up, so this is the original."
    safe = raw.replace("</transcript", "< /transcript")  # the transcript is untrusted data and must not close its own delimiter
    try:
        out = call_llm(db, workspace_id, "voice.cleanup", system=dv.CLEANUP_SYSTEM, user=f"<transcript>\n{safe}\n</transcript>",
                       schema=CleanOut, max_tokens=min(1200, len(raw) + 100))
    except LLMUnavailable:
        return None, "Cleanup was unavailable, so this is the original."
    cleaned = out.text.strip()
    verdict = dv.check_cleanup(raw, cleaned)
    if not verdict.ok:
        return None, f"Cleanup was not applied ({dv.REASON_TEXT[verdict.reason]}), so this is the original."
    return (None, None) if cleaned == raw else (cleaned, None)


@queue.handler("voice_transcribe")
def run_transcribe(db: Session, job: Job) -> None:
    assert job.workspace_id is not None
    row = VoiceRepo(db, job.workspace_id).get(uuid.UUID(job.payload["id"]), mine=False)
    if row is None or row.status not in LIVE or row.audio is None:
        return  # cancelled, cleared or already handled
    audio, kind = row.audio, dv.sniff_audio(row.audio)
    row.status = "processing"
    db.commit()
    stt, t0, failure, text = get_stt(), time.perf_counter(), None, ""
    try:
        if stt is None or kind is None:
            raise STTError("voice_disabled", "Voice input has been switched off on this server.")
        lang, prompt = dv.stt_options(row.language)
        text = stt.transcribe(audio, mime=kind.mime, ext=kind.ext, language=lang, prompt=prompt)
    except STTError as exc:
        failure = exc
    except Exception as exc:  # noqa: BLE001 - the audio is wiped below, so a retry could not succeed: record the failure instead
        log.warning("voice %s: speech provider crashed (%s)", row.id, type(exc).__name__)
        failure = STTError("internal", "Transcription failed unexpectedly. Your text was not changed; try again.")
    finally:
        row.audio = None  # raw audio never outlives processing, success or failure
        db.flush()
    latency = int((time.perf_counter() - t0) * 1000)
    db.add(AIUsageRecord(workspace_id=row.workspace_id, task="voice.stt", model=stt.name if stt else "none", ok=failure is None,
                         error=failure.code if failure else None, latency_ms=latency))
    db.refresh(row)
    if row.status != "processing":  # the user cancelled or cleared while we were working: keep nothing
        VoiceRepo(db, row.workspace_id).scrub(row, row.status)
        return
    if failure is not None:
        _fail(row, failure.code, failure.message)
    else:
        raw = dv.normalize_transcript(text)
        if not raw:
            _fail(row, "no_speech", "No speech was detected. Check your microphone and try again.")
        else:
            row.raw_text, row.provider, note = raw, stt.name if stt else None, dv.script_note(row.language, raw)
            if row.cleanup_requested:
                row.clean_text, cleanup_note = _cleanup(db, row.workspace_id, raw)
                note = cleanup_note or note
            row.cleanup_note, row.status = (note or None), "done"
            row.finished_at = datetime.now(timezone.utc)
    # ids, sizes, status and timing only: never audio, never transcript text
    log.info("voice %s %s: %d bytes in, %d chars out, %d ms", row.id, row.status, row.audio_bytes, len(row.raw_text or ""), latency)


def housekeeping(db: Session) -> None:
    gone, wiped = purge_expired(db, get_settings().voice_retention_hours)
    db.commit()
    if gone or wiped:
        log.info("voice purge: %d rows deleted, %d stray audio blobs wiped", gone, wiped)
