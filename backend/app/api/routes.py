import csv
import io
import uuid

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.api.deps import COOKIE, Ctx, err, get_ctx, require_admin
from app.api.schemas import (
    BatchOut,
    JobOut,
    LeadDetail,
    LeadOut,
    LeadPage,
    LeadPatch,
    LoginIn,
    MappingIn,
    SuppressionIn,
    SuppressionOut,
)
from app.core.config import get_settings
from app.core.security import make_session_token, verify_password
from app.db import get_db
from app.domain import normalize as n
from app.domain.states import MANUAL_TARGETS, IllegalTransition, check_transition
from app.jobs import queue
from app.models import ActivityLog, Company, ImportBatch, ImportRowError, Job, Lead, User
from app.repos.leads import LeadRepo
from app.repos.suppression import SuppressionRepo
from app.services import imports as imp
from app.services.audit import activity, audit

router = APIRouter()


# ---------- auth ----------
@router.post("/auth/login")
def login(body: LoginIn, response: Response, db: Session = Depends(get_db)):
    user = db.scalars(select(User).where(User.email == body.email.strip().lower())).first()
    if not user or not user.is_active or not verify_password(user.password_hash, body.password):
        audit(db, None, None, "auth.login_failed")
        db.commit()
        raise err(401, "bad_credentials", "invalid email or password")
    s = get_settings()
    response.set_cookie(COOKIE, make_session_token(user.id), httponly=True, samesite="lax",
                        secure=s.cookie_secure, max_age=s.session_ttl_hours * 3600)
    return {"ok": True}


@router.post("/auth/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE)
    return {"ok": True}


@router.get("/me")
def me(ctx: Ctx = Depends(get_ctx)):
    return {"id": ctx.user.id, "email": ctx.user.email, "workspace_id": ctx.workspace_id, "role": ctx.role}


# ---------- imports ----------
def _batch(ctx: Ctx, batch_id: uuid.UUID) -> ImportBatch:
    b = ctx.db.scalars(select(ImportBatch).where(
        ImportBatch.id == batch_id, ImportBatch.workspace_id == ctx.workspace_id)).first()
    if not b:
        raise err(404, "not_found", "import not found")
    return b


@router.post("/imports")
async def upload_import(file: UploadFile = File(...), default_region: str | None = Form(None),
                        ctx: Ctx = Depends(get_ctx)):
    data = await file.read(get_settings().max_upload_bytes + 1)
    try:
        batch = imp.create_batch(ctx.db, ctx.workspace_id, ctx.user.id, file.filename or "upload.csv",
                                 data, default_region)
    except imp.ImportError_ as e:
        raise err(422, "bad_file", str(e)) from e
    ctx.db.commit()
    return {"batch": BatchOut.model_validate(batch), "preview": imp.preview(batch),
            "target_fields": imp.TARGET_FIELDS}


@router.put("/imports/{batch_id}/mapping", response_model=BatchOut)
def set_mapping(batch_id: uuid.UUID, body: MappingIn, ctx: Ctx = Depends(get_ctx)):
    b = _batch(ctx, batch_id)
    if b.status not in ("uploaded", "mapped"):
        raise err(409, "bad_state", "mapping can only change before the import starts")
    try:
        imp.validate_mapping(b.headers, body.mapping)
    except imp.ImportError_ as e:
        raise err(422, "bad_mapping", str(e)) from e
    b.mapping, b.status = body.mapping, "mapped"
    if body.default_region:
        b.default_region = body.default_region.upper()
    ctx.db.commit()
    return b


@router.post("/imports/{batch_id}/start", response_model=BatchOut)
def start_import(batch_id: uuid.UUID, ctx: Ctx = Depends(get_ctx)):
    b = _batch(ctx, batch_id)
    if b.status not in ("uploaded", "mapped"):
        raise err(409, "bad_state", f"import is {b.status}")
    try:
        imp.enqueue_import(ctx.db, b)
    except imp.ImportError_ as e:
        raise err(422, "bad_mapping", str(e)) from e
    audit(ctx.db, ctx.workspace_id, ctx.user.id, "import.start", str(b.id))
    ctx.db.commit()
    return b


@router.get("/imports/{batch_id}", response_model=BatchOut)
def get_import(batch_id: uuid.UUID, ctx: Ctx = Depends(get_ctx)):
    return _batch(ctx, batch_id)


@router.get("/imports", response_model=list[BatchOut])
def list_imports(ctx: Ctx = Depends(get_ctx)):
    return list(ctx.db.scalars(select(ImportBatch).where(ImportBatch.workspace_id == ctx.workspace_id)
                               .order_by(ImportBatch.created_at.desc()).limit(50)))


@router.post("/imports/{batch_id}/retry-failed", response_model=BatchOut)
def retry_failed(batch_id: uuid.UUID, ctx: Ctx = Depends(get_ctx)):
    b = _batch(ctx, batch_id)
    if b.status != "completed":
        raise err(409, "bad_state", "can only retry a completed import")
    imp.enqueue_import(ctx.db, b, mode="retry")
    ctx.db.commit()
    return b


@router.get("/imports/{batch_id}/errors.csv", response_class=PlainTextResponse)
def errors_csv(batch_id: uuid.UUID, ctx: Ctx = Depends(get_ctx)):
    b = _batch(ctx, batch_id)
    errs = list(ctx.db.scalars(select(ImportRowError).where(ImportRowError.batch_id == b.id)
                               .order_by(ImportRowError.row_number)))
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["row_number", "kind", "reason", *b.headers])
    for e in errs:
        w.writerow([e.row_number, e.kind, n.csv_safe(e.reason), *[n.csv_safe(e.raw.get(h, "")) for h in b.headers]])
    return PlainTextResponse(out.getvalue(), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="import-{b.id}-errors.csv"'})


# ---------- leads ----------
@router.get("/leads", response_model=LeadPage)
def list_leads(q: str | None = None, status: str | None = None, region: str | None = None,
               batch_id: uuid.UUID | None = None, cursor: str | None = None,
               limit: int = Query(50, ge=1, le=200), ctx: Ctx = Depends(get_ctx)):
    try:
        items, nxt = LeadRepo(ctx.db, ctx.workspace_id).list(
            q=q, status=status, region=region, batch_id=batch_id, cursor=cursor, limit=limit)
    except ValueError as e:
        raise err(422, "bad_cursor", "invalid cursor") from e
    return LeadPage(items=[LeadOut.model_validate(i) for i in items], next_cursor=nxt)


@router.get("/leads/{lead_id}", response_model=LeadDetail)
def get_lead(lead_id: uuid.UUID, ctx: Ctx = Depends(get_ctx)):
    lead = LeadRepo(ctx.db, ctx.workspace_id).get(lead_id)
    if not lead:
        raise err(404, "not_found", "lead not found")
    detail = LeadDetail.model_validate(lead)
    if lead.company_id:
        c = ctx.db.get(Company, lead.company_id)
        if c and c.workspace_id == ctx.workspace_id:
            detail.company = {"id": str(c.id), "name": c.name, "domain": c.domain,
                              "website": c.website, "location": c.location, "industry": c.industry}
    logs = ctx.db.scalars(select(ActivityLog).where(
        ActivityLog.workspace_id == ctx.workspace_id, ActivityLog.lead_id == lead.id)
        .order_by(ActivityLog.id.desc()).limit(100))
    detail.timeline = [{"kind": a.kind, "data": a.data, "at": a.created_at.isoformat()} for a in logs]
    from app.services.research import evidence_for
    detail.evidence = [{"id": str(e.id), "finding": e.finding, "excerpt": e.excerpt, "url": e.url, "kind": e.kind,
                        "confidence": e.confidence, "retrieved_at": e.retrieved_at.isoformat()} for e in evidence_for(ctx.db, ctx.workspace_id, lead.id)]
    detail.icp_breakdown = lead.icp_breakdown or []
    return detail


@router.post("/leads/{lead_id}/research")
def research_lead_now(lead_id: uuid.UUID, force: bool = False, ctx: Ctx = Depends(get_ctx)):
    from app.services.research import enqueue_research
    if not LeadRepo(ctx.db, ctx.workspace_id).get(lead_id):
        raise err(404, "not_found", "lead not found")
    enqueue_research(ctx.db, ctx.workspace_id, [lead_id], force)
    ctx.db.commit()
    return {"queued": 1}


class BulkResearch(BaseModel):
    lead_ids: list[uuid.UUID] = Field(max_length=2000)
    force: bool = False


@router.post("/leads/research")
def research_bulk(body: BulkResearch, ctx: Ctx = Depends(get_ctx)):
    from app.services.research import enqueue_research
    repo = LeadRepo(ctx.db, ctx.workspace_id)
    ids = [i for i in body.lead_ids if repo.get(i)]
    enqueue_research(ctx.db, ctx.workspace_id, ids, body.force)
    ctx.db.commit()
    return {"queued": len(ids)}


@router.patch("/leads/{lead_id}", response_model=LeadOut)
def patch_lead(lead_id: uuid.UUID, body: LeadPatch, ctx: Ctx = Depends(get_ctx)):
    lead = LeadRepo(ctx.db, ctx.workspace_id).get(lead_id)
    if not lead:
        raise err(404, "not_found", "lead not found")
    changes = body.model_dump(exclude_unset=True)
    new_status = changes.pop("status", None)
    if "region" in changes and changes["region"]:
        changes["region"] = changes["region"].upper()
    for k, v in changes.items():
        setattr(lead, k, v)
    if new_status and new_status != lead.status:
        if new_status not in MANUAL_TARGETS:
            raise err(422, "status_not_manual", f"{new_status} cannot be set manually")
        try:
            check_transition(lead.status, new_status)
        except IllegalTransition as e:
            raise err(409, "illegal_transition", str(e)) from e
        old, lead.status = lead.status, new_status
        if new_status in ("unsubscribed", "suppressed"):
            lead.opted_out = True
            sup = SuppressionRepo(ctx.db, ctx.workspace_id)
            if lead.email_norm:
                sup.add("email", lead.email_norm, "manual", f"lead:{lead.id}")
            if lead.phone_e164:
                sup.add("phone", lead.phone_e164, "manual", f"lead:{lead.id}")
        activity(ctx.db, ctx.workspace_id, lead.id, "lead.status_changed", old=old, new=new_status,
                 by=str(ctx.user.id))
        audit(ctx.db, ctx.workspace_id, ctx.user.id, "lead.status", str(lead.id), old=old, new=new_status)
    if changes:
        activity(ctx.db, ctx.workspace_id, lead.id, "lead.edited", fields=sorted(changes))
    ctx.db.commit()
    return lead


# ---------- suppression ----------
@router.get("/suppressions", response_model=list[SuppressionOut])
def list_suppressions(ctx: Ctx = Depends(get_ctx)):
    return SuppressionRepo(ctx.db, ctx.workspace_id).list()


@router.post("/suppressions", response_model=list[SuppressionOut])
def add_suppression(body: SuppressionIn, ctx: Ctx = Depends(get_ctx)):
    repo = SuppressionRepo(ctx.db, ctx.workspace_id)
    value = repo.add_raw(body.kind, body.value, body.reason, f"user:{ctx.user.id}")
    if value is None:
        raise err(422, "bad_value", f"invalid {body.kind}")
    # Existing leads matching the value stop being contactable immediately.
    col = {"email": Lead.email_norm, "phone": Lead.phone_e164}.get(body.kind)
    if col is not None:
        ctx.db.execute(update(Lead).where(Lead.workspace_id == ctx.workspace_id, col == value,
                       Lead.status.notin_(["unsubscribed", "suppressed", "bounced"]))
                       .values(status="suppressed", opted_out=True))
    audit(ctx.db, ctx.workspace_id, ctx.user.id, "suppression.add", value, kind=body.kind, reason=body.reason)
    ctx.db.commit()
    return repo.list()


@router.delete("/suppressions/{rec_id}")
def remove_suppression(rec_id: uuid.UUID, ctx: Ctx = Depends(require_admin)):
    repo = SuppressionRepo(ctx.db, ctx.workspace_id)
    rec = repo.get(rec_id)
    if not rec:
        raise err(404, "not_found", "suppression record not found")
    audit(ctx.db, ctx.workspace_id, ctx.user.id, "suppression.remove", rec.value_norm,
          kind=rec.kind, reason=rec.reason)
    ctx.db.delete(rec)  # lead statuses are NOT auto-restored; that needs explicit review
    ctx.db.commit()
    return {"ok": True}


# ---------- jobs ----------
@router.get("/jobs", response_model=list[JobOut])
def list_jobs(state: str | None = None, ctx: Ctx = Depends(get_ctx)):
    stmt = select(Job).where(Job.workspace_id == ctx.workspace_id)
    if state:
        stmt = stmt.where(Job.state == state)
    return list(ctx.db.scalars(stmt.order_by(Job.created_at.desc()).limit(100)))


@router.post("/jobs/{job_id}/retry", response_model=JobOut)
def retry_job(job_id: uuid.UUID, ctx: Ctx = Depends(get_ctx)):
    job = ctx.db.scalars(select(Job).where(Job.id == job_id, Job.workspace_id == ctx.workspace_id)).first()
    if not job:
        raise err(404, "not_found", "job not found")
    if job.state != "dead":
        raise err(409, "bad_state", "only dead jobs can be retried")
    queue.retry_dead(ctx.db, job)
    audit(ctx.db, ctx.workspace_id, ctx.user.id, "job.retry", str(job.id))
    ctx.db.commit()
    return job
