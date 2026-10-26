import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.deps import Ctx, err, get_ctx
from app.db import must_get
from app.domain.normalize import blank
from app.domain.states import can_transition
from app.jobs import queue
from app.models import (
    Campaign,
    CampaignLead,
    ChannelAccount,
    Company,
    Conversation,
    GeneratedMessage,
    Lead,
    Message,
    ResearchEvidence,
    ScheduledAction,
)
from app.repos.leads import LeadRepo
from app.services import personalize, research, sending
from app.services.audit import activity, audit

router = APIRouter()
CHANNELS = {"email", "linkedin", "instagram"}


class CampaignIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    offer: str = ""
    objective: str = "Book a short intro call"
    tone: str = "friendly, concise, professional"
    sender_name: str = ""
    sender_company: str = ""
    physical_address: str = ""
    timezone: str = "UTC"
    work_start: int = Field(9, ge=0, le=23)
    work_end: int = Field(17, ge=1, le=24)
    daily_limit: int = Field(30, ge=1, le=500)
    channels: list[str] = ["email"]
    sequence: list[dict[str, int]] = [{"step": 0, "day": 0}, {"step": 1, "day": 3}, {"step": 2, "day": 7}]
    icp: dict[str, Any] = {}
    thresholds: dict[str, Any] = {}
    blocked_regions: list[str] = ["GB", "DE", "FR", "IT", "ES", "NL", "IE", "CA"]
    channel_account_id: uuid.UUID | None = None


class CampaignPatch(BaseModel):
    name: str | None = None
    offer: str | None = None
    objective: str | None = None
    tone: str | None = None
    sender_name: str | None = None
    sender_company: str | None = None
    physical_address: str | None = None
    timezone: str | None = None
    work_start: int | None = Field(None, ge=0, le=23)
    work_end: int | None = Field(None, ge=1, le=24)
    daily_limit: int | None = Field(None, ge=1, le=500)
    channels: list[str] | None = None
    sequence: list[dict[str, int]] | None = None
    icp: dict[str, Any] | None = None
    thresholds: dict[str, Any] | None = None
    blocked_regions: list[str] | None = None
    channel_account_id: uuid.UUID | None = None


def _validate(c: CampaignIn | CampaignPatch) -> None:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
    if c.timezone:
        try:
            ZoneInfo(c.timezone)
        except (ZoneInfoNotFoundError, ValueError):
            raise err(422, "bad_timezone", f"unknown timezone {c.timezone}")
    if c.channels is not None and (not c.channels or not set(c.channels) <= CHANNELS):
        raise err(422, "bad_channels", f"channels must be a non-empty subset of {sorted(CHANNELS)}")
    if c.sequence is not None:
        steps = [s.get("step", -1) for s in c.sequence]  # a missing step becomes -1 and fails the "starts at 0" check below (422, not a crash)
        if not c.sequence or steps != sorted(set(steps)) or steps[0] != 0 or any(s.get("day", -1) < 0 for s in c.sequence):
            raise err(422, "bad_sequence", "sequence needs ascending unique steps starting at 0 with day >= 0")
    if c.work_start is not None and c.work_end is not None and c.work_start >= c.work_end:
        raise err(422, "bad_hours", "work_start must be before work_end")


def camp_dict(db, c: Campaign) -> dict:
    counts = dict(db.execute(select(CampaignLead.state, func.count()).where(CampaignLead.campaign_id == c.id).group_by(CampaignLead.state)).all())
    msgs = dict(db.execute(select(GeneratedMessage.status, func.count()).where(GeneratedMessage.campaign_id == c.id).group_by(GeneratedMessage.status)).all())
    d = {k: getattr(c, k) for k in ["id", "name", "status", "offer", "objective", "tone", "sender_name", "sender_company",
                                      "physical_address", "timezone", "work_start", "work_end", "daily_limit", "channels",
                                      "sequence", "icp", "thresholds", "blocked_regions", "channel_account_id", "created_at"]}
    d["lead_counts"], d["message_counts"] = counts, msgs
    return d


def get_campaign(ctx: Ctx, cid: uuid.UUID) -> Campaign:
    c = ctx.db.scalars(select(Campaign).where(Campaign.id == cid, Campaign.workspace_id == ctx.workspace_id, Campaign.deleted_at.is_(None))).first()
    if not c:
        raise err(404, "not_found", "campaign not found")
    return c


def _check_account(ctx: Ctx, account_id: uuid.UUID | None) -> None:
    if account_id and not ctx.db.scalars(select(ChannelAccount.id).where(ChannelAccount.id == account_id, ChannelAccount.workspace_id == ctx.workspace_id)).first():
        raise err(422, "bad_account", "channel account not found")


@router.post("/campaigns")
def create_campaign(body: CampaignIn, ctx: Ctx = Depends(get_ctx)):
    _validate(body)
    _check_account(ctx, body.channel_account_id)
    c = Campaign(workspace_id=ctx.workspace_id, **body.model_dump())
    ctx.db.add(c)
    ctx.db.flush()
    audit(ctx.db, ctx.workspace_id, ctx.user.id, "campaign.create", str(c.id), name=c.name)
    ctx.db.commit()
    return camp_dict(ctx.db, c)


@router.get("/campaigns")
def list_campaigns(ctx: Ctx = Depends(get_ctx)):
    rows = ctx.db.scalars(select(Campaign).where(Campaign.workspace_id == ctx.workspace_id, Campaign.deleted_at.is_(None)).order_by(Campaign.created_at.desc()))
    return [camp_dict(ctx.db, c) for c in rows]


@router.get("/campaigns/{cid}")
def get_one(cid: uuid.UUID, ctx: Ctx = Depends(get_ctx)):
    return camp_dict(ctx.db, get_campaign(ctx, cid))


@router.patch("/campaigns/{cid}")
def patch_campaign(cid: uuid.UUID, body: CampaignPatch, ctx: Ctx = Depends(get_ctx)):
    c = get_campaign(ctx, cid)
    _validate(body)
    changes = body.model_dump(exclude_unset=True)
    _check_account(ctx, changes.get("channel_account_id"))
    if c.status == "active" and ({"sequence", "channels", "channel_account_id"} & set(changes)):
        raise err(409, "bad_state", "pause the campaign before changing its sequence, channels or sending account")
    for k, v in changes.items():
        setattr(c, k, v)
    audit(ctx.db, ctx.workspace_id, ctx.user.id, "campaign.update", str(c.id), fields=sorted(changes))
    ctx.db.commit()
    return camp_dict(ctx.db, c)


class AddLeads(BaseModel):
    lead_ids: list[uuid.UUID] | None = None
    status: str | None = None
    batch_id: uuid.UUID | None = None
    region: str | None = None


@router.post("/campaigns/{cid}/leads")
def add_leads(cid: uuid.UUID, body: AddLeads, ctx: Ctx = Depends(get_ctx)):
    c = get_campaign(ctx, cid)
    repo = LeadRepo(ctx.db, ctx.workspace_id)
    if body.lead_ids:
        leads = [l for l in (repo.get(i) for i in body.lead_ids) if l]
    elif body.status or body.batch_id or body.region:
        leads, cur = [], None
        while True:
            page, cur = repo.list(status=body.status, region=body.region, batch_id=body.batch_id, cursor=cur, limit=200)
            leads += page
            if not cur:
                break
    else:
        raise err(422, "no_selection", "pass lead_ids or a filter (status, batch_id, region)")
    existing = set(ctx.db.scalars(select(CampaignLead.lead_id).where(CampaignLead.campaign_id == c.id)))
    added = skipped = 0
    for l in leads:
        if l.id in existing or l.opted_out or l.status in ("suppressed", "unsubscribed", "bounced"):
            skipped += 1
            continue
        ctx.db.add(CampaignLead(workspace_id=ctx.workspace_id, campaign_id=c.id, lead_id=l.id))
        added += 1
    audit(ctx.db, ctx.workspace_id, ctx.user.id, "campaign.add_leads", str(c.id), added=added, skipped=skipped)
    ctx.db.commit()
    return {"added": added, "skipped": skipped}


@router.get("/campaigns/{cid}/leads")
def campaign_leads(cid: uuid.UUID, ctx: Ctx = Depends(get_ctx), limit: int = Query(200, le=500)):
    c = get_campaign(ctx, cid)
    rows = ctx.db.execute(select(CampaignLead, Lead, Company).join(Lead, Lead.id == CampaignLead.lead_id)
                          .outerjoin(Company, Company.id == Lead.company_id).where(CampaignLead.campaign_id == c.id)
                          .order_by(CampaignLead.icp_score.desc().nullslast(), CampaignLead.created_at).limit(limit)).all()
    return [{"lead_id": str(l.id), "name": " ".join(x for x in [l.first_name, l.last_name] if x) or None, "email": l.email_norm,
             "company": co.name if co else None, "domain": co.domain if co else None, "lead_status": l.status,
             "research_status": l.research_status, "state": cl.state, "stop_reason": cl.stop_reason, "icp_score": cl.icp_score,
             "icp_class": cl.icp_class, "icp_confidence": cl.icp_confidence, "icp_breakdown": cl.icp_breakdown} for cl, l, co in rows]


def _enqueue(ctx: Ctx, c: Campaign, kind: str, payload: dict | None = None) -> dict:
    job = queue.enqueue(ctx.db, kind, {"campaign_id": str(c.id), **(payload or {})}, ctx.workspace_id, max_attempts=3)
    ctx.db.commit()
    return {"job_id": str(job.id), "type": kind}


@router.post("/campaigns/{cid}/research")
def campaign_research(cid: uuid.UUID, force: bool = False, ctx: Ctx = Depends(get_ctx)):
    c = get_campaign(ctx, cid)
    ids = list(ctx.db.scalars(select(CampaignLead.lead_id).where(CampaignLead.campaign_id == c.id)))
    n = research.enqueue_research(ctx.db, ctx.workspace_id, ids, force)
    ctx.db.commit()
    return {"queued": n}


@router.post("/campaigns/{cid}/qualify")
def campaign_qualify(cid: uuid.UUID, ctx: Ctx = Depends(get_ctx)):
    return _enqueue(ctx, get_campaign(ctx, cid), "qualify_campaign")


class GenIn(BaseModel):
    include_insufficient: bool = False
    regenerate: bool = False


@router.post("/campaigns/{cid}/generate-messages")
def campaign_generate(cid: uuid.UUID, body: GenIn = GenIn(), ctx: Ctx = Depends(get_ctx)):
    return _enqueue(ctx, get_campaign(ctx, cid), "generate_messages", body.model_dump())


@router.get("/campaigns/{cid}/readiness")
def readiness(cid: uuid.UUID, ctx: Ctx = Depends(get_ctx)):
    c = get_campaign(ctx, cid)
    acct = ctx.db.get(ChannelAccount, c.channel_account_id) if c.channel_account_id else None
    approved = ctx.db.scalar(select(func.count()).select_from(GeneratedMessage).where(
        GeneratedMessage.campaign_id == c.id, GeneratedMessage.status == "approved", GeneratedMessage.channel == "email")) or 0
    checks = [
        {"key": "offer", "label": "Offer text written", "ok": bool(c.offer.strip())},
        {"key": "address", "label": "Physical postal address set (email footer)", "ok": bool(c.physical_address.strip())},
        {"key": "sender", "label": "Sender name set", "ok": bool(c.sender_name.strip())},
        {"key": "account", "label": "Sending account selected and active", "ok": bool(acct and acct.status == "active")},
        {"key": "approved", "label": f"At least one approved email draft ({approved} approved)", "ok": approved > 0},
    ]
    needed = checks if "email" in c.channels else checks[:3]
    return {"ready": all(x["ok"] for x in needed), "checks": needed}


@router.post("/campaigns/{cid}/launch")
def launch(cid: uuid.UUID, ctx: Ctx = Depends(get_ctx)):
    c = get_campaign(ctx, cid)
    if c.status == "active":
        raise err(409, "bad_state", "campaign is already active")
    r = readiness(cid, ctx)
    if not r["ready"]:
        raise err(422, "not_ready", "campaign is not ready to launch", checks=[x for x in r["checks"] if not x["ok"]])
    c.status = "active"
    n = 0
    for cl in ctx.db.scalars(select(CampaignLead).where(CampaignLead.campaign_id == c.id, CampaignLead.state.in_(["queued", "active"]))):
        lead = ctx.db.get(Lead, cl.lead_id)
        if lead and ensure_for(ctx, c, lead):
            cl.state = "active"
            n += 1
    audit(ctx.db, ctx.workspace_id, ctx.user.id, "campaign.launch", str(c.id), scheduled=n)
    ctx.db.commit()
    return {"status": "active", "scheduled": n}


def ensure_for(ctx: Ctx, c: Campaign, lead: Lead) -> bool:
    ok = False
    for ch in c.channels:
        if ch == "email" and sending.ensure_scheduled(ctx.db, c, lead, ch):
            ok = True
    return ok


@router.post("/campaigns/{cid}/pause")
def pause(cid: uuid.UUID, ctx: Ctx = Depends(get_ctx)):
    c = get_campaign(ctx, cid)
    c.status = "paused"
    audit(ctx.db, ctx.workspace_id, ctx.user.id, "campaign.pause", str(c.id))
    ctx.db.commit()
    return {"status": c.status}


@router.post("/campaigns/{cid}/resume")
def resume(cid: uuid.UUID, ctx: Ctx = Depends(get_ctx)):
    c = get_campaign(ctx, cid)
    if c.status != "paused":
        raise err(409, "bad_state", "only a paused campaign can be resumed")
    c.status = "active"
    audit(ctx.db, ctx.workspace_id, ctx.user.id, "campaign.resume", str(c.id))
    ctx.db.commit()
    return {"status": c.status}


# ---------- messages ----------
def _msg_dict(db, gm: GeneratedMessage, lead: Lead | None = None, company: Company | None = None, with_evidence: bool = False) -> dict:
    d = {k: getattr(gm, k) for k in ["id", "campaign_id", "lead_id", "channel", "step", "version", "subject", "body", "rationale",
                                      "claims", "quality", "source", "status", "approved_at", "created_at", "content_hash", "approved_hash"]}
    d["edited_since_approval"] = bool(gm.approved_hash and gm.approved_hash != gm.content_hash)
    if lead:
        d["lead"] = {"id": str(lead.id), "name": " ".join(x for x in [lead.first_name, lead.last_name] if x) or None, "title": lead.title,
                     "email": lead.email_norm, "company": company.name if company else None, "domain": company.domain if company else None,
                     "linkedin_url": lead.linkedin_url, "instagram_url": lead.instagram_url, "region": lead.region}
    if with_evidence and gm.evidence_ids:
        ids = [uuid.UUID(i) for i in gm.evidence_ids]
        d["evidence"] = [{"id": str(e.id), "finding": e.finding, "excerpt": e.excerpt, "url": e.url, "kind": e.kind, "confidence": e.confidence}
                         for e in db.scalars(select(ResearchEvidence).where(ResearchEvidence.id.in_(ids)))]
    return d


def get_msg(ctx: Ctx, mid: uuid.UUID) -> GeneratedMessage:
    gm = ctx.db.scalars(select(GeneratedMessage).where(GeneratedMessage.id == mid, GeneratedMessage.workspace_id == ctx.workspace_id)).first()
    if not gm:
        raise err(404, "not_found", "message not found")
    return gm


@router.get("/messages")
def list_messages(campaign_id: uuid.UUID | None = None, status: str | None = None, channel: str | None = None,
                  lead_id: uuid.UUID | None = None, limit: int = Query(100, le=300), ctx: Ctx = Depends(get_ctx)):
    q = (select(GeneratedMessage, Lead, Company).join(Lead, Lead.id == GeneratedMessage.lead_id)
         .outerjoin(Company, Company.id == Lead.company_id).where(GeneratedMessage.workspace_id == ctx.workspace_id))
    for col, v in ((GeneratedMessage.campaign_id, campaign_id), (GeneratedMessage.status, status),
                   (GeneratedMessage.channel, channel), (GeneratedMessage.lead_id, lead_id)):
        if v:
            q = q.where(col == v)
    rows = ctx.db.execute(q.order_by(GeneratedMessage.step, GeneratedMessage.created_at.desc()).limit(limit)).all()
    return [_msg_dict(ctx.db, g, l, c) for g, l, c in rows]


@router.get("/messages/{mid}")
def get_message(mid: uuid.UUID, ctx: Ctx = Depends(get_ctx)):
    gm = get_msg(ctx, mid)
    lead = must_get(ctx.db, Lead, gm.lead_id)
    return _msg_dict(ctx.db, gm, lead, ctx.db.get(Company, lead.company_id) if lead.company_id else None, True)


class EditIn(BaseModel):
    subject: str | None = None
    body: str


@router.patch("/messages/{mid}")
def edit_message(mid: uuid.UUID, body: EditIn, ctx: Ctx = Depends(get_ctx)):
    gm = get_msg(ctx, mid)
    if gm.status == "sent":
        raise err(409, "bad_state", "a sent message cannot be edited")
    was = gm.status
    personalize.revalidate_after_edit(ctx.db, gm, blank(body.subject) if gm.channel == "email" else None, body.body)
    audit(ctx.db, ctx.workspace_id, ctx.user.id, "message.edit", str(gm.id), previous_status=was)
    ctx.db.commit()
    return _msg_dict(ctx.db, gm)


def _approve(ctx: Ctx, gm: GeneratedMessage) -> None:
    if gm.status not in ("draft", "needs_review"):
        raise err(409, "bad_state", f"message is {gm.status}")
    if gm.quality.get("errors"):
        raise err(422, "validation_errors", "fix the validation errors before approving", errors=gm.quality["errors"])
    lead = must_get(ctx.db, Lead, gm.lead_id)
    if lead.opted_out or lead.status in ("suppressed", "unsubscribed", "bounced"):
        raise err(409, "lead_suppressed", "this lead is suppressed and cannot be contacted")
    gm.status, gm.approved_hash, gm.approved_by, gm.approved_at = "approved", gm.content_hash, ctx.user.id, datetime.now(timezone.utc)
    if gm.step == 0 and lead.status in ("qualified", "ready_for_review"):
        if lead.status == "qualified" and can_transition("qualified", "ready_for_review"):
            lead.status = "ready_for_review"
        if can_transition(lead.status, "approved"):
            lead.status = "approved"
    activity(ctx.db, ctx.workspace_id, gm.lead_id, "message.approved", message=str(gm.id), step=gm.step)
    audit(ctx.db, ctx.workspace_id, ctx.user.id, "message.approve", str(gm.id), hash=gm.content_hash[:12])
    camp = must_get(ctx.db, Campaign, gm.campaign_id)
    if camp.status == "active" and gm.channel == "email":
        sending.ensure_scheduled(ctx.db, camp, lead, gm.channel)  # approving a later step schedules it


@router.post("/messages/{mid}/approve")
def approve_message(mid: uuid.UUID, ctx: Ctx = Depends(get_ctx)):
    gm = get_msg(ctx, mid)
    _approve(ctx, gm)
    ctx.db.commit()
    return _msg_dict(ctx.db, gm)


@router.post("/messages/{mid}/reject")
def reject_message(mid: uuid.UUID, ctx: Ctx = Depends(get_ctx)):
    gm = get_msg(ctx, mid)
    if gm.status == "sent":
        raise err(409, "bad_state", "already sent")
    gm.status, gm.approved_hash = "rejected", None
    for a in ctx.db.scalars(select(ScheduledAction).where(ScheduledAction.generated_message_id == gm.id, ScheduledAction.state == "pending")):
        a.state, a.last_error = "cancelled", "message rejected"
    audit(ctx.db, ctx.workspace_id, ctx.user.id, "message.reject", str(gm.id))
    ctx.db.commit()
    return _msg_dict(ctx.db, gm)


class BulkApprove(BaseModel):
    message_ids: list[uuid.UUID] | None = None
    all_clean: bool = False  # every draft in the campaign with no errors and at least one verified claim (step 0) 


@router.post("/campaigns/{cid}/approve")
def bulk_approve(cid: uuid.UUID, body: BulkApprove, ctx: Ctx = Depends(get_ctx)):
    c = get_campaign(ctx, cid)
    q = select(GeneratedMessage).where(GeneratedMessage.campaign_id == c.id, GeneratedMessage.workspace_id == ctx.workspace_id,
                                       GeneratedMessage.status.in_(["draft", "needs_review"]))
    if body.message_ids:
        q = q.where(GeneratedMessage.id.in_(body.message_ids))
    elif not body.all_clean:
        raise err(422, "no_selection", "pass message_ids or all_clean=true")
    ok = skipped = 0
    for gm in ctx.db.scalars(q):
        clean = not gm.quality.get("errors") and (gm.step > 0 or gm.quality.get("verified_claims", 0) > 0)
        if body.all_clean and not clean:
            skipped += 1
            continue
        try:
            _approve(ctx, gm)
            ok += 1
        except Exception:  # HTTPException from _approve: skip, report
            skipped += 1
    ctx.db.commit()
    return {"approved": ok, "skipped": skipped}


@router.post("/messages/{mid}/send")
def send_message(mid: uuid.UUID, ctx: Ctx = Depends(get_ctx)):
    """Never sends inline: schedules through the queue; the worker's policy gate makes the final decision."""
    gm = get_msg(ctx, mid)
    if gm.channel != "email":
        raise err(409, "manual_channel", f"{gm.channel} is a manual channel: copy the draft and use the manual queue")
    if gm.status != "approved" or gm.approved_hash != gm.content_hash:
        raise err(409, "not_approved", "only an approved, unedited message can be queued")
    camp = must_get(ctx.db, Campaign, gm.campaign_id)
    lead = must_get(ctx.db, Lead, gm.lead_id)
    a = sending.ensure_scheduled(ctx.db, camp, lead, gm.channel)
    if a is None:
        raise err(409, "nothing_to_schedule", "no unsent approved step is next in the sequence for this lead")
    a.run_at = datetime.now(timezone.utc)
    ctx.db.commit()
    return {"action_id": str(a.id), "state": a.state, "note": "queued; the worker will re-check policy before sending"}


# ---------- manual channels (LinkedIn / Instagram) ----------
@router.get("/manual-queue")
def manual_queue(ctx: Ctx = Depends(get_ctx)):
    rows = ctx.db.execute(select(GeneratedMessage, Lead, Company).join(Lead, Lead.id == GeneratedMessage.lead_id)
                          .outerjoin(Company, Company.id == Lead.company_id)
                          .where(GeneratedMessage.workspace_id == ctx.workspace_id, GeneratedMessage.channel.in_(["linkedin", "instagram"]),
                                 GeneratedMessage.status == "approved")
                          .order_by(GeneratedMessage.created_at)).all()
    today = datetime.now(timezone.utc) - timedelta(days=1)
    done_today = ctx.db.scalar(select(func.count()).select_from(Message).where(
        Message.workspace_id == ctx.workspace_id, Message.manual.is_(True), Message.created_at >= today)) or 0
    return {"items": [_msg_dict(ctx.db, g, l, c) for g, l, c in rows if not (l.opted_out or l.status in ("suppressed", "unsubscribed", "bounced"))],
            "sent_last_24h": done_today, "suggested_daily_cap": 20,
            "note": "You send these yourself in your own browser. FlowHQ never logs into or automates LinkedIn or Instagram."}


@router.post("/messages/{mid}/mark-sent")
def mark_sent(mid: uuid.UUID, ctx: Ctx = Depends(get_ctx)):
    gm = get_msg(ctx, mid)
    if gm.channel not in ("linkedin", "instagram") or gm.status != "approved":
        raise err(409, "bad_state", "only approved LinkedIn/Instagram drafts can be marked as sent")
    lead = must_get(ctx.db, Lead, gm.lead_id)
    if lead.opted_out or lead.status in ("suppressed", "unsubscribed", "bounced"):
        raise err(409, "lead_suppressed", "lead is suppressed")
    conv = ctx.db.scalars(select(Conversation).where(Conversation.lead_id == lead.id, Conversation.campaign_id == gm.campaign_id, Conversation.channel == gm.channel)).first()
    if not conv:
        conv = Conversation(workspace_id=ctx.workspace_id, lead_id=lead.id, campaign_id=gm.campaign_id, channel=gm.channel)
        ctx.db.add(conv)
        ctx.db.flush()
    now = datetime.now(timezone.utc)
    ctx.db.add(Message(workspace_id=ctx.workspace_id, conversation_id=conv.id, lead_id=lead.id, campaign_id=gm.campaign_id,
                       generated_message_id=gm.id, direction="out", channel=gm.channel, body=gm.body, state="sent", manual=True,
                       sent_at=now, idempotency_key=f"manual:{gm.id}"))
    gm.status = "sent"
    conv.last_message_at = now
    if lead.status == "approved" and can_transition("approved", "active_outreach"):
        lead.status = "active_outreach"
    activity(ctx.db, ctx.workspace_id, lead.id, "message.sent_manual", channel=gm.channel)
    audit(ctx.db, ctx.workspace_id, ctx.user.id, "message.mark_sent", str(gm.id), channel=gm.channel)
    ctx.db.commit()
    return {"ok": True}


# ---------- scheduled actions / failures ----------
@router.get("/actions")
def list_actions(state: str | None = None, ctx: Ctx = Depends(get_ctx), limit: int = Query(100, le=300)):
    q = (select(ScheduledAction, Lead, Company, Campaign).join(Lead, Lead.id == ScheduledAction.lead_id).outerjoin(Company, Company.id == Lead.company_id)
         .join(Campaign, Campaign.id == ScheduledAction.campaign_id).where(ScheduledAction.workspace_id == ctx.workspace_id))
    if state == "problem":
        q = q.where(ScheduledAction.state.in_(["failed", "needs_manual_check"]))
    elif state:
        q = q.where(ScheduledAction.state == state)
    rows = ctx.db.execute(q.order_by(ScheduledAction.run_at).limit(limit)).all()
    return [{"id": str(a.id), "state": a.state, "step": a.step, "channel": a.channel, "run_at": a.run_at, "retry_count": a.retry_count,
             "last_error": a.last_error, "lead_id": str(l.id), "lead": l.email_norm, "company": co.name if co else None,
             "campaign": c.name, "campaign_id": str(c.id)} for a, l, co, c in rows]


@router.post("/actions/{aid}/retry")
def retry_action(aid: uuid.UUID, ctx: Ctx = Depends(get_ctx)):
    a = ctx.db.scalars(select(ScheduledAction).where(ScheduledAction.id == aid, ScheduledAction.workspace_id == ctx.workspace_id)).first()
    if not a:
        raise err(404, "not_found", "action not found")
    if a.state != "failed":
        raise err(409, "bad_state", "only failed actions can be retried")
    a.state, a.retry_count, a.run_at, a.last_error = "pending", 0, datetime.now(timezone.utc), None
    audit(ctx.db, ctx.workspace_id, ctx.user.id, "action.retry", str(a.id))
    ctx.db.commit()
    return {"ok": True}


class ResolveIn(BaseModel):
    was_sent: bool


@router.post("/actions/{aid}/resolve")
def resolve_action(aid: uuid.UUID, body: ResolveIn, ctx: Ctx = Depends(get_ctx)):
    """For needs_manual_check: the operator verified at the provider whether the email actually went out."""
    a = ctx.db.scalars(select(ScheduledAction).where(ScheduledAction.id == aid, ScheduledAction.workspace_id == ctx.workspace_id)).first()
    if not a or a.state != "needs_manual_check":
        raise err(404, "not_found", "no such action needing a manual check")
    m = ctx.db.scalars(select(Message).where(Message.idempotency_key == a.idempotency_key)).first()
    if body.was_sent:
        a.state = "sent"
        if m:
            m.state, m.sent_at = "sent", m.sent_at or datetime.now(timezone.utc)
        gm = must_get(ctx.db, GeneratedMessage, a.generated_message_id)
        gm.status = "sent"
    else:
        a.state, a.run_at, a.last_error = "pending", datetime.now(timezone.utc), None
        if m:
            m.state = "failed"
    audit(ctx.db, ctx.workspace_id, ctx.user.id, "action.resolve", str(a.id), was_sent=body.was_sent)
    ctx.db.commit()
    return {"ok": True}
