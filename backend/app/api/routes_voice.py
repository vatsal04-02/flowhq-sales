"""Voice dictation API. Authenticated only. Upload queues a job; the browser polls for the text.
Nothing here can send a message: the result is plain text that the user reviews and inserts into a field."""
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel

from app.api.deps import Ctx, err, get_ctx
from app.core.config import get_settings
from app.models import VoiceTranscription
from app.repos.voice import LIVE, VoiceRepo
from app.services import voice as svc
from app.services.audit import audit

router = APIRouter()


class VoiceOut(BaseModel):
    id: uuid.UUID
    status: str                      # queued | processing | done | failed | cancelled | cleared
    language: str
    text: str | None = None          # what to offer the user: the cleaned text if cleanup was applied, else the original
    raw_text: str | None = None      # always the recogniser's own words
    cleaned: bool = False
    cleanup_requested: bool = False
    note: str | None = None          # why cleanup was skipped, or a script warning
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime | None = None


def _out(row: VoiceTranscription) -> VoiceOut:
    done = row.status == "done"
    return VoiceOut(id=row.id, status=row.status, language=row.language,
                    text=(row.clean_text or row.raw_text) if done else None, raw_text=row.raw_text if done else None,
                    cleaned=bool(done and row.clean_text), cleanup_requested=row.cleanup_requested, note=row.cleanup_note if done else None,
                    error_code=row.error_code, error_message=row.error_message, created_at=row.created_at)


def _mine(ctx: Ctx, vid: uuid.UUID) -> VoiceTranscription:
    row = VoiceRepo(ctx.db, ctx.workspace_id, ctx.user.id).get(vid)
    if row is None:
        raise err(404, "not_found", "dictation not found")
    return row


@router.get("/voice/status")
def voice_status(ctx: Ctx = Depends(get_ctx)):
    return svc.info(ctx.db, ctx.workspace_id, ctx.user.id)


@router.post("/voice/transcriptions", status_code=202, response_model=VoiceOut)
async def upload(file: UploadFile = File(...), language: str = Form("auto"), cleanup: bool = Form(False),
                 duration_ms: int | None = Form(None), ctx: Ctx = Depends(get_ctx)):
    data = await file.read(get_settings().voice_max_bytes + 1)
    try:
        row = svc.submit(ctx.db, ctx.workspace_id, ctx.user.id, data, language, cleanup, duration_ms)
    except svc.VoiceError as e:
        raise err(e.status, e.code, e.message) from e
    ctx.db.commit()
    return _out(row)


@router.get("/voice/transcriptions", response_model=list[VoiceOut])
def recent(ctx: Ctx = Depends(get_ctx)):
    return [_out(r) for r in VoiceRepo(ctx.db, ctx.workspace_id, ctx.user.id).recent()]


@router.get("/voice/transcriptions/{vid}", response_model=VoiceOut)
def get_one(vid: uuid.UUID, ctx: Ctx = Depends(get_ctx)):
    row = _mine(ctx, vid)
    svc.expire_if_stuck(row)
    ctx.db.commit()
    return _out(row)


@router.delete("/voice/transcriptions/{vid}")
def discard(vid: uuid.UUID, ctx: Ctx = Depends(get_ctx)):
    """Cancel a dictation in flight, or discard a finished one. Content is dropped immediately."""
    row = _mine(ctx, vid)
    VoiceRepo(ctx.db, ctx.workspace_id, ctx.user.id).scrub(row, "cancelled" if row.status in LIVE else "cleared")
    ctx.db.commit()
    return {"ok": True}


@router.delete("/voice/transcriptions")
def clear_history(ctx: Ctx = Depends(get_ctx)):
    n = VoiceRepo(ctx.db, ctx.workspace_id, ctx.user.id).clear_history()
    audit(ctx.db, ctx.workspace_id, ctx.user.id, "voice.clear_history", None, count=n)
    ctx.db.commit()
    return {"cleared": n}
