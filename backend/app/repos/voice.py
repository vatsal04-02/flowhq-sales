import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, cast

from sqlalchemy import delete, func, select, update
from sqlalchemy.engine import CursorResult, Result
from sqlalchemy.orm import Session

from app.models import VoiceTranscription

LIVE = ("queued", "processing")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _rows(res: Result[Any]) -> int:
    return int(cast(CursorResult[Any], res).rowcount or 0)


class VoiceRepo:
    """Every query is scoped to the workspace and, for user-facing reads, to the dictating user."""

    def __init__(self, db: Session, workspace_id: uuid.UUID, user_id: uuid.UUID | None = None):
        self.db, self.ws, self.user = db, workspace_id, user_id

    def get(self, vid: uuid.UUID, *, mine: bool = True) -> VoiceTranscription | None:
        q = select(VoiceTranscription).where(VoiceTranscription.id == vid, VoiceTranscription.workspace_id == self.ws)
        if mine:
            q = q.where(VoiceTranscription.user_id == self.user)
        return self.db.scalars(q).first()

    def count_last_hour(self) -> int:
        return self.db.scalar(select(func.count()).select_from(VoiceTranscription).where(
            VoiceTranscription.user_id == self.user, VoiceTranscription.created_at > _now() - timedelta(hours=1))) or 0

    def recent(self, limit: int = 20) -> list[VoiceTranscription]:
        return list(self.db.scalars(select(VoiceTranscription).where(
            VoiceTranscription.user_id == self.user, VoiceTranscription.workspace_id == self.ws, VoiceTranscription.status == "done")
            .order_by(VoiceTranscription.created_at.desc()).limit(limit)))

    def history_count(self) -> int:
        return self.db.scalar(select(func.count()).select_from(VoiceTranscription).where(
            VoiceTranscription.user_id == self.user, VoiceTranscription.workspace_id == self.ws, VoiceTranscription.status == "done")) or 0

    def scrub(self, row: VoiceTranscription, status: str) -> None:
        """Drop all content but keep the skeleton, which still counts toward the hourly limit until the purge removes it."""
        row.status, row.audio, row.raw_text, row.clean_text, row.cleanup_note = status, None, None, None, None
        row.finished_at = row.finished_at or _now()

    def clear_history(self) -> int:
        n = self.db.execute(update(VoiceTranscription).where(
            VoiceTranscription.user_id == self.user, VoiceTranscription.workspace_id == self.ws,
            VoiceTranscription.status.in_(("done", "failed")))
            .values(status="cleared", audio=None, raw_text=None, clean_text=None, cleanup_note=None))
        return _rows(n)


def purge_expired(db: Session, retention_hours: int, stale_minutes: int = 15) -> tuple[int, int]:
    """(rows deleted, stray audio blobs wiped). Cross-workspace by design: it is housekeeping, not a user query."""
    now = _now()
    cutoff = now - timedelta(minutes=stale_minutes)
    wiped = db.execute(update(VoiceTranscription).where(
        VoiceTranscription.audio.is_not(None), VoiceTranscription.created_at < cutoff).values(audio=None))
    # a live row this old means the worker never finished it; its audio is gone, so it is failed rather than left hanging
    db.execute(update(VoiceTranscription).where(
        VoiceTranscription.status.in_(LIVE), VoiceTranscription.created_at < cutoff)
        .values(status="failed", error_code="timeout", error_message="Transcription did not finish in time.", finished_at=now))
    gone = db.execute(delete(VoiceTranscription).where(
        VoiceTranscription.created_at < now - timedelta(hours=max(retention_hours, 2))))
    return _rows(gone), _rows(wiped)
