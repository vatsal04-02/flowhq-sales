import json
import smtplib
import ssl
import uuid
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.adapters.channels.base import Outbound, SendError, adapter_for, capabilities_for
from app.adapters.channels.imap import ImapError
from app.api.deps import Ctx, err, get_ctx, require_admin
from app.core.config import get_settings
from app.core.crypto import decrypt, encrypt
from app.db import get_db
from app.domain import intent as I
from app.domain.states import can_transition
from app.models import (
    AIUsageRecord,
    AuditLog,
    Campaign,
    ChannelAccount,
    Company,
    Conversation,
    Lead,
    Message,
    Opportunity,
    ProviderEvent,
    Workspace,
)
from app.repos.suppression import SuppressionRepo
from app.services import analytics, mailsync, replies, sending
from app.services.audit import activity, audit

router = APIRouter()


# ---------- inbox ----------
def _conv_dict(db, conv: Conversation, lead: Lead, company: Company | None, last: Message | None) -> dict:
    return {"id": str(conv.id), "channel": conv.channel, "subject": conv.subject, "status": conv.status, "last_message_at": conv.last_message_at,
            "lead": {"id": str(lead.id), "name": " ".join(x for x in [lead.first_name, lead.last_name] if x) or lead.email_norm,
                     "email": lead.email_norm, "title": lead.title, "company": company.name if company else None, "status": lead.status},
            "last": {"direction": last.direction, "preview": last.body[:140], "intent": last.intent, "simulated": last.simulated} if last else None}


@router.get("/conversations")
def conversations(intent: str | None = None, limit: int = Query(100, le=300), ctx: Ctx = Depends(get_ctx)):
    rows = ctx.db.execute(select(Conversation, Lead, Company).join(Lead, Lead.id == Conversation.lead_id).outerjoin(Company, Company.id == Lead.company_id)
                          .where(Conversation.workspace_id == ctx.workspace_id).order_by(Conversation.last_message_at.desc()).limit(limit)).all()
    out = []
    for c, l, co in rows:
        last = ctx.db.scalars(select(Message).where(Message.conversation_id == c.id).order_by(Message.created_at.desc())).first()
        if intent and not (last and last.intent == intent):
            continue
        out.append(_conv_dict(ctx.db, c, l, co, last))
    return out


def _conv(ctx: Ctx, cid: uuid.UUID) -> Conversation:
    c = ctx.db.scalars(select(Conversation).where(Conversation.id == cid, Conversation.workspace_id == ctx.workspace_id)).first()
    if not c:
        raise err(404, "not_found", "conversation not found")
    return c


@router.get("/conversations/{cid}")
def conversation(cid: uuid.UUID, ctx: Ctx = Depends(get_ctx)):
    c = _conv(ctx, cid)
    lead = ctx.db.get(Lead, c.lead_id)
    co = ctx.db.get(Company, lead.company_id) if lead.company_id else None
    msgs = ctx.db.scalars(select(Message).where(Message.conversation_id == c.id).order_by(Message.created_at))
    camp = ctx.db.get(Campaign, c.campaign_id) if c.campaign_id else None
    return {**_conv_dict(ctx.db, c, lead, co, None), "campaign": camp.name if camp else None, "intents": [r[0] for r in I.RULES] + ["unclear"],
            "messages": [{"id": str(m.id), "direction": m.direction, "subject": m.subject, "body": m.body, "state": m.state, "simulated": m.simulated,
                          "manual": m.manual, "peer": m.peer, "at": m.sent_at or m.created_at, "intent": m.intent, "intent_confidence": m.intent_confidence,
                          "intent_source": m.intent_source, "suggested_reply": m.suggested_reply, "error": m.error} for m in msgs]}


class ReplyIn(BaseModel):
    body: str = Field(min_length=1, max_length=5000)


@router.post("/conversations/{cid}/reply")
def reply(cid: uuid.UUID, body: ReplyIn, ctx: Ctx = Depends(get_ctx)):
    """Human-written reply. Still passes suppression, kill-switch and capability checks; never bypasses them."""
    c = _conv(ctx, cid)
    lead = ctx.db.get(Lead, c.lead_id)
    ws = ctx.db.get(Workspace, ctx.workspace_id)
    camp = ctx.db.get(Campaign, c.campaign_id) if c.campaign_id else None
    acct = ctx.db.get(ChannelAccount, camp.channel_account_id) if camp and camp.channel_account_id else None
    if ws.kill_switch:
        raise err(409, "kill_switch", "global kill switch is on")
    if lead.opted_out or SuppressionRepo(ctx.db, ctx.workspace_id).is_suppressed(lead.email_norm, lead.phone_e164):
        raise err(409, "lead_suppressed", "this lead opted out or is suppressed; replying is blocked")
    if c.channel != "email" or not acct or not capabilities_for("email", acct.provider).can_send:
        raise err(409, "cannot_send", "this conversation has no sending account; copy your reply and send it manually")
    last_in = ctx.db.scalars(select(Message).where(Message.conversation_id == c.id).order_by(Message.created_at.desc())).first()
    key = f"reply:{uuid.uuid4()}"
    msg = Message(workspace_id=ctx.workspace_id, conversation_id=c.id, lead_id=lead.id, campaign_id=c.campaign_id, channel_account_id=acct.id,
                  direction="out", channel="email", subject=f"Re: {c.subject or ''}".strip(), body=body.body, state="sending", idempotency_key=key,
                  message_id_header=f"<{uuid.uuid4().hex}@{acct.from_email.split('@')[-1]}>",
                  in_reply_to=(last_in.message_id_header if last_in and last_in.direction == "out" else last_in.in_reply_to if last_in else None))
    ctx.db.add(msg)
    ctx.db.commit()
    creds = json.loads(decrypt(acct.credentials_enc)) if acct.credentials_enc else None
    try:
        res = adapter_for(acct.provider, creds).send(Outbound(to=lead.email_norm, from_email=acct.from_email, from_name=camp.sender_name if camp else "",
                                                              subject=msg.subject, body=msg.body + f"\n\n--\nUnsubscribe: {sending.unsub_url(lead.workspace_id, lead.id)}",
                                                              message_id=msg.message_id_header, in_reply_to=msg.in_reply_to,
                                                              list_unsubscribe_url=sending.unsub_url(lead.workspace_id, lead.id)), key)
    except SendError as e:
        msg.state, msg.error = "failed", str(e)[:400]
        ctx.db.commit()
        raise err(502, "send_failed", f"provider rejected the reply: {e}")
    msg.state, msg.sent_at, msg.simulated, msg.provider_message_id = "sent", datetime.now(timezone.utc), res.simulated, res.provider_message_id
    c.last_message_at = msg.sent_at
    audit(ctx.db, ctx.workspace_id, ctx.user.id, "reply.sent", str(msg.id), lead=str(lead.id))
    ctx.db.commit()
    return {"id": str(msg.id), "state": msg.state, "simulated": msg.simulated}


class ClassifyIn(BaseModel):
    message_id: uuid.UUID
    intent: str


@router.post("/conversations/{cid}/classify")
def classify(cid: uuid.UUID, body: ClassifyIn, ctx: Ctx = Depends(get_ctx)):
    c = _conv(ctx, cid)
    m = ctx.db.scalars(select(Message).where(Message.id == body.message_id, Message.conversation_id == c.id, Message.direction == "in")).first()
    if not m:
        raise err(404, "not_found", "inbound message not found")
    if body.intent not in [r[0] for r in I.RULES] + ["unclear"]:
        raise err(422, "bad_intent", "unknown intent")
    replies.reclassify(ctx.db, m, body.intent, ctx.user.id)
    ctx.db.commit()
    return {"intent": m.intent, "source": m.intent_source}


# ---------- sandbox (mock provider only; simulated results are always labelled) ----------
class SimReply(BaseModel):
    lead_id: uuid.UUID
    body: str
    external_id: str | None = None


def _sandbox_conv(ctx: Ctx, lead_id: uuid.UUID) -> tuple[Lead, Conversation]:
    lead = ctx.db.scalars(select(Lead).where(Lead.id == lead_id, Lead.workspace_id == ctx.workspace_id)).first()
    conv = ctx.db.scalars(select(Conversation).where(Conversation.lead_id == lead_id, Conversation.workspace_id == ctx.workspace_id)
                          .order_by(Conversation.last_message_at.desc())).first() if lead else None
    if not lead or not conv:
        raise err(404, "not_found", "no conversation for this lead")
    acct_id = ctx.db.scalar(select(Message.channel_account_id).where(Message.conversation_id == conv.id, Message.channel_account_id.isnot(None)))
    acct = ctx.db.get(ChannelAccount, acct_id) if acct_id else None
    if not acct or acct.provider != "mock":
        raise err(409, "not_sandbox", "simulation is only available for conversations sent through the mock sandbox account")
    return lead, conv


@router.post("/sandbox/simulate-reply")
def simulate_reply(body: SimReply, ctx: Ctx = Depends(get_ctx)):
    lead, conv = _sandbox_conv(ctx, body.lead_id)
    last_out = ctx.db.scalars(select(Message).where(Message.conversation_id == conv.id, Message.direction == "out", Message.state == "sent")
                              .order_by(Message.created_at.desc())).first()
    m = replies.ingest_inbound(ctx.db, ctx.workspace_id, provider="mock", external_id=body.external_id or f"sim-{uuid.uuid4()}",
                               from_email=lead.email_norm or "", subject=f"Re: {conv.subject or ''}", body=body.body,
                               in_reply_to=last_out.message_id_header if last_out else None, simulated=True)
    ctx.db.commit()
    return {"duplicate_ignored": m is None, "intent": m.intent if m else None}


@router.post("/sandbox/simulate-bounce")
def simulate_bounce(lead_id: uuid.UUID, ctx: Ctx = Depends(get_ctx)):
    lead, _ = _sandbox_conv(ctx, lead_id)
    ok = replies.ingest_bounce(ctx.db, ctx.workspace_id, provider="mock", external_id=f"bounce-{uuid.uuid4()}", email=lead.email_norm or "")
    ctx.db.commit()
    return {"processed": ok}


# ---------- pipeline ----------
STAGES = analytics.STAGES
STAGE_TO_LEAD = {"meeting_booked": "meeting_booked", "won": "converted", "lost": "not_interested"}


class OppIn(BaseModel):
    lead_id: uuid.UUID
    stage: str = "new"
    value: int | None = Field(None, ge=0)
    notes: str | None = None
    next_action_at: datetime | None = None


class OppPatch(BaseModel):
    stage: str | None = None
    value: int | None = Field(None, ge=0)
    notes: str | None = None
    next_action_at: datetime | None = None
    owner_id: uuid.UUID | None = None


def _opp(ctx: Ctx, oid: uuid.UUID) -> Opportunity:
    o = ctx.db.scalars(select(Opportunity).where(Opportunity.id == oid, Opportunity.workspace_id == ctx.workspace_id)).first()
    if not o:
        raise err(404, "not_found", "opportunity not found")
    return o


def _opp_dict(o: Opportunity, l: Lead, c: Company | None) -> dict:
    return {"id": str(o.id), "stage": o.stage, "value": o.value, "notes": o.notes, "next_action_at": o.next_action_at, "owner_id": o.owner_id,
            "lead": {"id": str(l.id), "name": " ".join(x for x in [l.first_name, l.last_name] if x) or l.email_norm, "email": l.email_norm,
                     "company": c.name if c else None, "outreach_status": l.status}}


@router.get("/opportunities")
def list_opps(ctx: Ctx = Depends(get_ctx)):
    rows = ctx.db.execute(select(Opportunity, Lead, Company).join(Lead, Lead.id == Opportunity.lead_id).outerjoin(Company, Company.id == Lead.company_id)
                          .where(Opportunity.workspace_id == ctx.workspace_id).order_by(Opportunity.updated_at.desc())).all()
    return {"stages": STAGES, "items": [_opp_dict(o, l, c) for o, l, c in rows]}


@router.post("/opportunities")
def create_opp(body: OppIn, ctx: Ctx = Depends(get_ctx)):
    if body.stage not in STAGES:
        raise err(422, "bad_stage", f"stage must be one of {STAGES}")
    lead = ctx.db.scalars(select(Lead).where(Lead.id == body.lead_id, Lead.workspace_id == ctx.workspace_id)).first()
    if not lead:
        raise err(404, "not_found", "lead not found")
    o = Opportunity(workspace_id=ctx.workspace_id, **body.model_dump())
    ctx.db.add(o)
    activity(ctx.db, ctx.workspace_id, lead.id, "opportunity.created", stage=o.stage, by=str(ctx.user.id))
    ctx.db.commit()
    return _opp_dict(o, lead, ctx.db.get(Company, lead.company_id) if lead.company_id else None)


@router.patch("/opportunities/{oid}")
def patch_opp(oid: uuid.UUID, body: OppPatch, ctx: Ctx = Depends(get_ctx)):
    o = _opp(ctx, oid)
    ch = body.model_dump(exclude_unset=True)
    if "stage" in ch and ch["stage"] not in STAGES:
        raise err(422, "bad_stage", f"stage must be one of {STAGES}")
    lead = ctx.db.get(Lead, o.lead_id)
    if ch.get("stage") and ch["stage"] != o.stage:
        activity(ctx.db, ctx.workspace_id, lead.id, "opportunity.stage", old=o.stage, new=ch["stage"], by=str(ctx.user.id))
        tgt = STAGE_TO_LEAD.get(ch["stage"])
        if tgt:  # opportunity stage is separate from outreach status; only mirror when the transition table allows
            sending.stop_sequences(ctx.db, ctx.workspace_id, lead.id, f"opportunity:{ch['stage']}")
            if lead.status != tgt and can_transition(lead.status, tgt):
                lead.status = tgt
    for k, v in ch.items():
        setattr(o, k, v)
    ctx.db.commit()
    return _opp_dict(o, lead, ctx.db.get(Company, lead.company_id) if lead.company_id else None)


# ---------- integrations / settings ----------
class SMTPIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    from_email: str
    host: str
    port: int = 587
    username: str = ""
    password: str = ""
    security: str = Field("starttls", pattern="^(starttls|ssl|none)$")
    daily_limit: int = Field(30, ge=1, le=2000)
    # optional: read replies and bounces from this mailbox (IMAP). Read-only; mail is never marked read, moved or deleted.
    imap_host: str = ""
    imap_port: int = 993
    imap_username: str = ""  # defaults to the SMTP username
    imap_password: str = ""  # defaults to the SMTP password
    imap_security: str = Field("ssl", pattern="^(starttls|ssl|none)$")


def _acct_dict(a: ChannelAccount) -> dict:
    caps = capabilities_for(a.channel, a.provider)
    reply_sync = mailsync.imap_config(a) is not None
    imap_h = (a.health or {}).get("imap") or {}
    return {"id": str(a.id), "provider": a.provider, "channel": a.channel, "name": a.name, "from_email": a.from_email, "status": a.status,
            "daily_limit": a.daily_limit, "health": a.health, "simulated": a.provider == "mock",
            "capabilities": {"can_send": caps.can_send, "can_receive": caps.can_receive or reply_sync or a.provider == "mock", "syncs_delivery": caps.syncs_delivery},
            "reply_sync": {"enabled": reply_sync, "ok": imap_h.get("ok"), "error": imap_h.get("error"), "checked_at": imap_h.get("checked_at"),
                           "new": imap_h.get("new"), "last_uid": (a.sync_state or {}).get("last_uid")}}


def _llm_health() -> dict:
    s = get_settings()
    if s.llm_provider != "ollama":
        return {"provider": s.llm_provider, "status": "templates_only" if s.llm_provider == "none" else s.llm_provider, "model": None}
    try:
        r = httpx.get(f"{s.llm_base_url.rstrip('/')}/models", timeout=2)
        models = [m.get("id") for m in r.json().get("data", [])]
        return {"provider": "ollama", "model": s.llm_model, "status": "ok" if s.llm_model in models else "model_missing", "available_models": models[:10]}
    except (httpx.HTTPError, ValueError):
        return {"provider": "ollama", "model": s.llm_model, "status": "unreachable",
                "hint": "Start Ollama and run `ollama pull " + s.llm_model + "`. Until then drafts use templates."}


@router.get("/integrations")
def integrations(ctx: Ctx = Depends(get_ctx)):
    accts = ctx.db.scalars(select(ChannelAccount).where(ChannelAccount.workspace_id == ctx.workspace_id).order_by(ChannelAccount.created_at))
    usage = ctx.db.execute(select(func.count(), func.coalesce(func.avg(AIUsageRecord.latency_ms), 0), func.count().filter(AIUsageRecord.ok.is_(False)))
                           .where(AIUsageRecord.workspace_id == ctx.workspace_id)).one()
    ws = ctx.db.get(Workspace, ctx.workspace_id)
    return {"accounts": [_acct_dict(a) for a in accts], "llm": _llm_health(),
            "llm_usage": {"calls": usage[0], "avg_latency_ms": int(usage[1]), "failures": usage[2]},
            "manual_channels": [{"channel": "linkedin", "mode": "manual-assist", "note": "Drafts + copy + mark-sent. No automation."},
                                {"channel": "instagram", "mode": "manual-assist", "note": "Drafts + copy + mark-sent. No automation."}],
            "kill_switch": ws.kill_switch}


@router.post("/integrations/mock")
def add_mock(ctx: Ctx = Depends(get_ctx)):
    a = ChannelAccount(workspace_id=ctx.workspace_id, provider="mock", name="Sandbox (simulated email)", from_email="sandbox@flowhq.test", daily_limit=1000)
    ctx.db.add(a)
    audit(ctx.db, ctx.workspace_id, ctx.user.id, "integration.add", "mock")
    ctx.db.commit()
    return _acct_dict(a)


@router.post("/integrations/smtp")
def add_smtp(body: SMTPIn, ctx: Ctx = Depends(require_admin)):
    from app.domain.normalize import normalize_email
    if not normalize_email(body.from_email):
        raise err(422, "bad_email", "from_email is not a valid address")
    payload = {k: getattr(body, k) for k in ("host", "port", "username", "password", "security")}
    if body.imap_host.strip():
        payload["imap"] = {"host": body.imap_host.strip(), "port": body.imap_port, "username": body.imap_username or body.username,
                           "password": body.imap_password or body.password, "security": body.imap_security}
    creds = encrypt(json.dumps(payload))
    a = ChannelAccount(workspace_id=ctx.workspace_id, provider="smtp", name=body.name, from_email=body.from_email, credentials_enc=creds, daily_limit=body.daily_limit)
    ctx.db.add(a)
    audit(ctx.db, ctx.workspace_id, ctx.user.id, "integration.add", "smtp", host=body.host, reply_sync=bool(body.imap_host.strip()))
    if body.imap_host.strip():
        mailsync.enqueue_sync(ctx.db, a)  # first sync sets the cursor; only the last few days are looked at
    ctx.db.commit()
    return _acct_dict(a)


def _acct(ctx: Ctx, aid: uuid.UUID) -> ChannelAccount:
    a = ctx.db.scalars(select(ChannelAccount).where(ChannelAccount.id == aid, ChannelAccount.workspace_id == ctx.workspace_id)).first()
    if not a:
        raise err(404, "not_found", "account not found")
    return a


@router.post("/integrations/{aid}/test")
def test_account(aid: uuid.UUID, ctx: Ctx = Depends(get_ctx)):
    a = _acct(ctx, aid)
    now = datetime.now(timezone.utc).isoformat()
    h = dict(a.health or {})
    if a.provider == "mock":
        h["smtp"] = {"ok": True, "checked_at": now, "note": "sandbox"}
    else:
        c = json.loads(decrypt(a.credentials_enc))
        try:
            srv = smtplib.SMTP_SSL(c["host"], c["port"], timeout=10) if c["security"] == "ssl" else smtplib.SMTP(c["host"], c["port"], timeout=10)
            with srv:
                if c["security"] == "starttls":
                    srv.starttls(context=ssl.create_default_context())
                if c.get("username"):
                    srv.login(c["username"], c["password"])
            h["smtp"] = {"ok": True, "checked_at": now}
        except (smtplib.SMTPException, OSError) as e:
            h["smtp"] = {"ok": False, "error": str(e)[:200], "checked_at": now}
        if c.get("imap"):
            try:
                n = mailsync.client_for(c["imap"]).check()
                h["imap"] = {**(h.get("imap") or {}), "ok": True, "error": None, "checked_at": now, "inbox_messages": n}
            except ImapError as e:
                h["imap"] = {**(h.get("imap") or {}), "ok": False, "error": str(e)[:200], "checked_at": now}
    a.health = h
    ctx.db.commit()
    return h


@router.post("/integrations/{aid}/sync")
def sync_now(aid: uuid.UUID, ctx: Ctx = Depends(get_ctx)):
    """Queue a mailbox check now (the worker also polls on its own)."""
    a = _acct(ctx, aid)
    if mailsync.imap_config(a) is None:
        raise err(409, "no_imap", "this account has no IMAP (reply sync) settings")
    job = mailsync.enqueue_sync(ctx.db, a, force=True)
    ctx.db.commit()
    return {"queued": True, "job_id": str(job.id) if job else None}


@router.get("/inbox/unmatched")
def unmatched(limit: int = Query(50, le=200), ctx: Ctx = Depends(get_ctx)):
    """Mail that arrived in a connected mailbox but could not be tied to any lead in this workspace."""
    rows = ctx.db.scalars(select(ProviderEvent).where(ProviderEvent.workspace_id == ctx.workspace_id,
                                                        ProviderEvent.kind.in_(["reply_unmatched", "bounce_unmatched"]))
                          .order_by(ProviderEvent.created_at.desc()).limit(limit))
    return [{"id": str(e.id), "kind": e.kind, "received_at": e.created_at, "from": e.payload.get("from") or e.payload.get("email"),
             "subject": e.payload.get("subject")} for e in rows]


@router.delete("/integrations/{aid}")
def delete_account(aid: uuid.UUID, ctx: Ctx = Depends(require_admin)):
    a = ctx.db.scalars(select(ChannelAccount).where(ChannelAccount.id == aid, ChannelAccount.workspace_id == ctx.workspace_id)).first()
    if not a:
        raise err(404, "not_found", "account not found")
    if ctx.db.scalars(select(Campaign.id).where(Campaign.channel_account_id == a.id, Campaign.status == "active").limit(1)).first():
        raise err(409, "in_use", "an active campaign uses this account; pause it first")
    a.status = "disabled"
    a.credentials_enc = None
    audit(ctx.db, ctx.workspace_id, ctx.user.id, "integration.remove", str(a.id))
    ctx.db.commit()
    return {"ok": True}


class KillIn(BaseModel):
    on: bool


@router.post("/workspace/kill-switch")
def kill_switch(body: KillIn, ctx: Ctx = Depends(get_ctx)):
    ws = ctx.db.get(Workspace, ctx.workspace_id)
    ws.kill_switch = body.on
    audit(ctx.db, ctx.workspace_id, ctx.user.id, "workspace.kill_switch", None, on=body.on)
    ctx.db.commit()
    return {"kill_switch": ws.kill_switch}


# ---------- analytics ----------
@router.get("/analytics/overview")
def a_overview(campaign_id: uuid.UUID | None = None, days: int | None = Query(None, ge=1, le=365), ctx: Ctx = Depends(get_ctx)):
    return analytics.overview(ctx.db, ctx.workspace_id, campaign_id, days)


@router.get("/analytics/campaigns")
def a_campaigns(ctx: Ctx = Depends(get_ctx)):
    return analytics.per_campaign(ctx.db, ctx.workspace_id)


@router.get("/analytics/channels")
def a_channels(ctx: Ctx = Depends(get_ctx)):
    return analytics.per_channel(ctx.db, ctx.workspace_id)


@router.get("/analytics/funnel")
def a_funnel(ctx: Ctx = Depends(get_ctx)):
    return analytics.overview(ctx.db, ctx.workspace_id)["funnel"]


@router.get("/analytics/timeseries")
def a_timeseries(days: int = Query(30, ge=1, le=365), ctx: Ctx = Depends(get_ctx)):
    return analytics.timeseries(ctx.db, ctx.workspace_id, days)


@router.get("/analytics/attention")
def a_attention(ctx: Ctx = Depends(get_ctx)):
    return analytics.needs_attention(ctx.db, ctx.workspace_id)


@router.get("/audit")
def audit_log(limit: int = Query(100, le=500), ctx: Ctx = Depends(get_ctx)):
    rows = ctx.db.scalars(select(AuditLog).where(AuditLog.workspace_id == ctx.workspace_id).order_by(AuditLog.id.desc()).limit(limit))
    return [{"id": a.id, "action": a.action, "target": a.target, "data": a.data, "actor_id": a.actor_id, "at": a.created_at} for a in rows]


# ---------- public unsubscribe (no auth; signed token; GET never changes state) ----------
_PAGE = "<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><title>Unsubscribe</title><body style='font-family:system-ui;max-width:28rem;margin:4rem auto;padding:0 1rem'>{}</body>"


@router.get("/u/{token}", response_class=HTMLResponse)
def unsub_page(token: str):
    if not sending.parse_unsub_token(token):
        return HTMLResponse(_PAGE.format("<h1>Link not valid</h1><p>This unsubscribe link is invalid or damaged.</p>"), status_code=400)
    return _PAGE.format(f"<h1>Unsubscribe</h1><p>Click below to stop receiving emails from us.</p><form method=post action='/api/v1/u/{token}'><button style='padding:.7rem 1.2rem;font-size:1rem'>Confirm unsubscribe</button></form>")


@router.post("/u/{token}", response_class=HTMLResponse)
def unsub_do(token: str, db: Session = Depends(get_db)):
    parsed = sending.parse_unsub_token(token)
    if not parsed:
        return HTMLResponse(_PAGE.format("<h1>Link not valid</h1>"), status_code=400)
    ws, lead_id = parsed
    lead = db.scalars(select(Lead).where(Lead.id == lead_id, Lead.workspace_id == ws)).first()
    if lead:
        sending.handle_unsubscribe(db, ws, lead, "unsubscribe_link")
        db.commit()
    return _PAGE.format("<h1>You're unsubscribed</h1><p>You won't receive further emails from us.</p>")
