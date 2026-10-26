"""The ONLY code path that sends. Every send passes the policy gate, is idempotent, and is recorded
before the network call so a crash can never cause a silent duplicate."""
import base64
import hashlib
import hmac
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.adapters.channels.base import Outbound, SendError, adapter_for, capabilities_for
from app.core.config import get_settings
from app.core.crypto import decrypt
from app.domain.policy import GateInput, check
from app.domain.states import can_transition
from app.models import (
    Campaign,
    CampaignLead,
    ChannelAccount,
    Conversation,
    GeneratedMessage,
    Lead,
    Message,
    ScheduledAction,
    Workspace,
)
from app.repos.suppression import SuppressionRepo
from app.services.audit import activity, audit

log = logging.getLogger("sending")
MAX_RETRIES = 4


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


# ---------- unsubscribe tokens ----------
def _sig(payload: str) -> str:
    return hmac.new(get_settings().secret_key.encode(), payload.encode(), hashlib.sha256).hexdigest()[:32]


def make_unsub_token(workspace_id: uuid.UUID, lead_id: uuid.UUID) -> str:
    body = base64.urlsafe_b64encode(json.dumps([str(workspace_id), str(lead_id)]).encode()).decode().rstrip("=")
    return f"{body}.{_sig(body)}"


def parse_unsub_token(token: str) -> tuple[uuid.UUID, uuid.UUID] | None:
    try:
        body, sig = token.rsplit(".", 1)
        if not hmac.compare_digest(sig, _sig(body)):
            return None
        ws, lead = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        return uuid.UUID(ws), uuid.UUID(lead)
    except (ValueError, TypeError):
        return None


def unsub_url(workspace_id: uuid.UUID, lead_id: uuid.UUID) -> str:
    return f"{get_settings().public_base_url.rstrip('/')}/api/v1/u/{make_unsub_token(workspace_id, lead_id)}"


def render_email_body(gm: GeneratedMessage, camp: Campaign, lead: Lead) -> str:
    footer = (f"\n\n--\n{camp.physical_address}\nIf you'd rather not hear from us, unsubscribe here: "
              f"{unsub_url(lead.workspace_id, lead.id)}")
    return gm.body + footer


# ---------- scheduling ----------
def _key(camp_id, lead_id, channel, step) -> str:
    return f"{camp_id}:{lead_id}:{channel}:{step}"


def ensure_scheduled(db: Session, camp: Campaign, lead: Lead, channel: str = "email") -> ScheduledAction | None:
    """Schedule the next approved, unsent step for this lead. Safe to call repeatedly (unique idempotency key)."""
    steps = sorted(camp.sequence, key=lambda s: s["step"])
    sent = db.scalars(select(GeneratedMessage).where(
        GeneratedMessage.campaign_id == camp.id, GeneratedMessage.lead_id == lead.id,
        GeneratedMessage.channel == channel, GeneratedMessage.status == "sent").order_by(GeneratedMessage.step.desc())).first()
    last_step = sent.step if sent else -1
    nxt = next((s for s in steps if s["step"] > last_step), None)
    if nxt is None:
        return None
    gm = db.scalars(select(GeneratedMessage).where(
        GeneratedMessage.campaign_id == camp.id, GeneratedMessage.lead_id == lead.id, GeneratedMessage.channel == channel,
        GeneratedMessage.step == nxt["step"], GeneratedMessage.status == "approved").order_by(GeneratedMessage.version.desc())).first()
    if gm is None or gm.approved_hash != gm.content_hash:
        return None
    key = _key(camp.id, lead.id, channel, nxt["step"])
    existing = db.scalars(select(ScheduledAction).where(ScheduledAction.idempotency_key == key)).first()
    if existing:
        return existing
    run_at = now_utc()
    if sent:
        prev_day = next((s["day"] for s in steps if s["step"] == sent.step), 0)
        last_msg = db.scalars(select(Message).where(Message.generated_message_id == sent.id, Message.direction == "out")
                              .order_by(Message.created_at.desc())).first()
        base = (last_msg.sent_at if last_msg and last_msg.sent_at else now_utc())
        run_at = base + timedelta(days=max(nxt["day"] - prev_day, 0))
    a = ScheduledAction(workspace_id=camp.workspace_id, lead_id=lead.id, campaign_id=camp.id, generated_message_id=gm.id,
                        step=nxt["step"], channel=channel, run_at=run_at, idempotency_key=key)
    db.add(a)
    db.flush()
    return a


def stop_sequences(db: Session, workspace_id: uuid.UUID, lead_id: uuid.UUID, reason: str, campaign_id: uuid.UUID | None = None) -> None:
    q = select(CampaignLead).where(CampaignLead.workspace_id == workspace_id, CampaignLead.lead_id == lead_id,
                                   CampaignLead.state.in_(["queued", "active"]))
    if campaign_id:
        q = q.where(CampaignLead.campaign_id == campaign_id)
    for cl in db.scalars(q):
        cl.state, cl.stop_reason = "stopped", reason
    aq = select(ScheduledAction).where(ScheduledAction.workspace_id == workspace_id, ScheduledAction.lead_id == lead_id,
                                       ScheduledAction.state.in_(["pending"]))
    if campaign_id:
        aq = aq.where(ScheduledAction.campaign_id == campaign_id)
    for a in db.scalars(aq):
        a.state, a.last_error = "cancelled", reason


# ---------- execution ----------
def _account_for(db: Session, camp: Campaign) -> ChannelAccount | None:
    return db.get(ChannelAccount, camp.channel_account_id) if camp.channel_account_id else None


def _sent_today(db: Session, filt, tz: str) -> int:
    start = datetime.now(ZoneInfo(tz)).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
    return db.scalar(select(func.count()).select_from(Message).where(
        Message.direction == "out", Message.manual.is_(False), Message.state.in_(["sending", "sent"]),
        Message.created_at >= start, filt)) or 0


def claim_due(db: Session, now: datetime | None = None) -> ScheduledAction | None:
    now = now or now_utc()
    a = db.scalars(select(ScheduledAction).where(or_(
        (ScheduledAction.state == "pending") & (ScheduledAction.run_at <= now),
        (ScheduledAction.state == "claiming") & (ScheduledAction.lease_until < now)))
        .order_by(ScheduledAction.run_at).limit(1).with_for_update(skip_locked=True)).first()
    if a is None:
        db.rollback()
        return None
    a.state, a.lease_until = "claiming", now + timedelta(minutes=5)
    db.commit()
    return a


def run_due(db: Session, limit: int = 25, now: datetime | None = None) -> int:
    n = 0
    while n < limit:
        a = claim_due(db, now)
        if a is None:
            break
        try:
            process_action(db, a, now or now_utc())
        except Exception as exc:  # noqa: BLE001 - never lose the action: record and retry later
            db.rollback()
            a = db.get(ScheduledAction, a.id)
            a.retry_count += 1
            a.last_error = f"{type(exc).__name__}: {exc}"[:500]
            a.state = "failed" if a.retry_count > MAX_RETRIES else "pending"
            a.run_at = now_utc() + timedelta(minutes=2 ** a.retry_count)
            log.exception("send action crashed")
        db.commit()
        n += 1
    return n


def process_action(db: Session, a: ScheduledAction, now: datetime) -> None:
    lead, camp, gm = db.get(Lead, a.lead_id), db.get(Campaign, a.campaign_id), db.get(GeneratedMessage, a.generated_message_id)
    ws = db.get(Workspace, a.workspace_id)
    cl = db.scalars(select(CampaignLead).where(CampaignLead.campaign_id == camp.id, CampaignLead.lead_id == lead.id)).first()

    existing = db.scalars(select(Message).where(Message.idempotency_key == a.idempotency_key)).first()
    if existing is not None:
        if existing.state == "sent":
            a.state, a.lease_until = "sent", None
            return
        if existing.state in ("sending", "needs_manual_check"):
            existing.state, a.state = "needs_manual_check", "needs_manual_check"
            a.last_error = "a previous attempt ended before its result was recorded; verify at the provider before resending"
            a.lease_until = None
            return

    acct = _account_for(db, camp)
    caps = capabilities_for(a.channel, acct.provider if acct else None)
    sup = SuppressionRepo(db, a.workspace_id).is_suppressed(lead.email_norm, lead.phone_e164)
    replied = db.scalar(select(func.count()).select_from(Message).where(   # an out-of-office auto-reply is not a reply
        Message.lead_id == lead.id, Message.direction == "in", Message.campaign_id == camp.id,
        Message.intent.is_distinct_from("out_of_office"))) > 0
    gate = GateInput(
        now=now, kill_switch=ws.kill_switch, campaign_status=camp.status, campaign_lead_state=cl.state if cl else "active",
        lead_status=lead.status, lead_opted_out=lead.opted_out, lead_region=lead.region, blocked_regions=camp.blocked_regions or [],
        suppressed_reason=sup, has_address=bool(camp.physical_address.strip()), recipient=lead.email_norm if a.channel == "email" else None,
        msg_status=gm.status, msg_hash=gm.content_hash, msg_approved_hash=gm.approved_hash,
        channel_can_send=caps.can_send, account_active=bool(acct and acct.status == "active"),
        sent_today_account=_sent_today(db, Message.channel_account_id == acct.id, camp.timezone) if acct else 0,
        account_daily_limit=acct.daily_limit if acct else 0,
        sent_today_campaign=_sent_today(db, Message.campaign_id == camp.id, camp.timezone), campaign_daily_limit=camp.daily_limit,
        timezone=camp.timezone, work_start=camp.work_start, work_end=camp.work_end, replied=replied)
    d = check(gate)

    if d.action == "defer":
        a.state, a.run_at, a.lease_until, a.last_error = "pending", d.until, None, d.reason
        return
    if d.action == "block":
        a.last_error, a.lease_until = d.reason, None
        if d.hold:
            a.state, a.run_at = "pending", now + timedelta(minutes=5)
        else:
            a.state = "cancelled"
            if cl:
                cl.state, cl.stop_reason = "stopped", d.reason[:50]
            activity(db, a.workspace_id, lead.id, "send.blocked", reason=d.reason, step=a.step)
        return

    # ---- allowed: record intent first, then call the provider ----
    conv = db.scalars(select(Conversation).where(Conversation.lead_id == lead.id, Conversation.campaign_id == camp.id,
                                                 Conversation.channel == a.channel)).first()
    if conv is None:
        conv = Conversation(workspace_id=a.workspace_id, lead_id=lead.id, campaign_id=camp.id, channel=a.channel, subject=gm.subject)
        db.add(conv)
        db.flush()
    prev_out = db.scalars(select(Message).where(Message.conversation_id == conv.id, Message.direction == "out", Message.state == "sent")
                          .order_by(Message.created_at.desc())).first()
    domain = acct.from_email.split("@")[-1]
    msg = existing or Message(workspace_id=a.workspace_id, conversation_id=conv.id, lead_id=lead.id, campaign_id=camp.id,
                              channel_account_id=acct.id, generated_message_id=gm.id, direction="out", channel=a.channel,
                              subject=gm.subject, body=render_email_body(gm, camp, lead), idempotency_key=a.idempotency_key,
                              message_id_header=f"<{uuid.uuid4().hex}@{domain}>",
                              in_reply_to=prev_out.message_id_header if prev_out else None)
    msg.state = "sending"
    db.add(msg)
    db.commit()  # the intent is durable BEFORE the network call

    creds = json.loads(decrypt(acct.credentials_enc)) if acct.credentials_enc else None
    try:
        res = adapter_for(acct.provider, creds).send(
            Outbound(to=lead.email_norm, from_email=acct.from_email, from_name=camp.sender_name, subject=msg.subject or "",
                     body=msg.body, message_id=msg.message_id_header, in_reply_to=msg.in_reply_to,
                     list_unsubscribe_url=unsub_url(lead.workspace_id, lead.id)), a.idempotency_key)
    except SendError as exc:
        msg = db.get(Message, msg.id)
        msg.state, msg.error = "failed", str(exc)[:500]
        if exc.permanent:
            a.state, a.last_error, a.lease_until = "failed", str(exc)[:500], None
            if "recipient" in str(exc).lower():
                handle_bounce(db, a.workspace_id, lead, "provider rejected recipient")
        else:
            a.retry_count += 1
            a.last_error, a.lease_until = str(exc)[:500], None
            a.state = "failed" if a.retry_count > MAX_RETRIES else "pending"
            a.run_at = now + timedelta(minutes=2 ** a.retry_count)
        return

    msg.state, msg.sent_at, msg.simulated = "sent", now, res.simulated
    msg.provider_message_id = res.provider_message_id
    conv.last_message_at = msg.sent_at
    gm.status = "sent"
    a.state, a.lease_until, a.last_error = "sent", None, None
    if cl:
        cl.state, cl.current_step = "active", a.step + 1
    if lead.status == "approved" and can_transition("approved", "active_outreach"):
        lead.status = "active_outreach"
    activity(db, a.workspace_id, lead.id, "message.sent", step=a.step, channel=a.channel, simulated=res.simulated)
    audit(db, a.workspace_id, None, "message.sent", str(msg.id), lead=str(lead.id), campaign=str(camp.id), simulated=res.simulated)
    db.flush()
    nxt = ensure_scheduled(db, camp, lead, a.channel)
    if nxt is None and cl:
        steps = sorted(s["step"] for s in camp.sequence)
        if a.step >= steps[-1]:
            cl.state = "completed"


# ---------- bounce / opt-out ----------
def handle_bounce(db: Session, workspace_id: uuid.UUID, lead: Lead, reason: str) -> None:
    if lead.email_norm:
        SuppressionRepo(db, workspace_id).add("email", lead.email_norm, "bounce", reason)
    lead.opted_out = True
    if lead.status != "bounced" and can_transition(lead.status, "bounced"):
        lead.status = "bounced"
    stop_sequences(db, workspace_id, lead.id, "bounced")
    activity(db, workspace_id, lead.id, "email.bounced", reason=reason)
    audit(db, workspace_id, None, "lead.bounced", str(lead.id), reason=reason)


def handle_unsubscribe(db: Session, workspace_id: uuid.UUID, lead: Lead, source: str, actor: uuid.UUID | None = None) -> None:
    repo = SuppressionRepo(db, workspace_id)
    if lead.email_norm:
        repo.add("email", lead.email_norm, "opt_out", source)
    if lead.phone_e164:
        repo.add("phone", lead.phone_e164, "opt_out", source)
    lead.opted_out = True
    if lead.status != "unsubscribed" and can_transition(lead.status, "unsubscribed"):
        lead.status = "unsubscribed"
    stop_sequences(db, workspace_id, lead.id, "unsubscribed")
    activity(db, workspace_id, lead.id, "lead.unsubscribed", source=source)
    audit(db, workspace_id, actor, "lead.unsubscribed", str(lead.id), source=source)
