"""Metrics with explicit numerators, denominators and windows. Lead-level and message-level counts are never mixed."""
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from app.domain.intent import POSITIVE
from app.models import AIUsageRecord, Campaign, ChannelAccount, Job, Lead, Message, Opportunity, ScheduledAction

STAGES = ["new", "qualified", "contacted", "engaged", "meeting_booked", "proposal", "won", "lost"]


def metric(value, numerator=None, denominator=None, definition="", window="all time") -> dict:
    rate = None if denominator in (None, 0) or numerator is None else round(100 * numerator / denominator, 1)
    return {"value": value if rate is None else rate, "numerator": numerator, "denominator": denominator, "unit": "count" if rate is None else "%",
            "definition": definition, "window": window}


def overview(db: Session, ws: uuid.UUID, campaign_id: uuid.UUID | None = None, days: int | None = None) -> dict:
    since = datetime.now(timezone.utc) - timedelta(days=days) if days else None
    win = f"last {days} days" if days else "all time"

    def lead_count(*conds):
        return db.scalar(select(func.count()).select_from(Lead).where(Lead.workspace_id == ws, Lead.deleted_at.is_(None), *conds)) or 0

    def msgs(direction, *conds, distinct_leads=False):
        col = distinct(Message.lead_id) if distinct_leads else Message.id
        q = select(func.count(col)).where(Message.workspace_id == ws, Message.direction == direction, *conds)
        if campaign_id:
            q = q.where(Message.campaign_id == campaign_id)
        if since:
            q = q.where(Message.created_at >= since)
        return db.scalar(q) or 0

    imported = lead_count()
    qualified = lead_count(Lead.icp_class.in_(["strong", "possible"]))
    from app.models import GeneratedMessage
    approved_leads = db.scalar(select(func.count(distinct(GeneratedMessage.lead_id))).where(
        GeneratedMessage.workspace_id == ws, GeneratedMessage.status.in_(["approved", "sent"]),
        *([GeneratedMessage.campaign_id == campaign_id] if campaign_id else []))) or 0
    sent_real = msgs("out", Message.state == "sent", Message.simulated.is_(False), Message.manual.is_(False))
    sent_sim = msgs("out", Message.state == "sent", Message.simulated.is_(True))
    sent_manual = msgs("out", Message.state == "sent", Message.manual.is_(True))
    contacted = msgs("out", Message.state == "sent", distinct_leads=True)
    replied = msgs("in", Message.intent.is_distinct_from("out_of_office"), distinct_leads=True)  # auto-replies are not replies
    positive = msgs("in", Message.intent.in_(list(POSITIVE)), distinct_leads=True)
    unsub = lead_count(Lead.status == "unsubscribed")
    bounced = lead_count(Lead.status == "bounced")
    oq = select(func.count()).select_from(Opportunity).where(Opportunity.workspace_id == ws)
    opps = db.scalar(oq) or 0
    meetings = db.scalar(oq.where(Opportunity.stage.in_(["meeting_booked", "proposal", "won"]))) or 0
    won = db.scalar(oq.where(Opportunity.stage == "won")) or 0
    return {
        "window": win, "campaign_id": str(campaign_id) if campaign_id else None,
        "cards": {
            "imported_leads": metric(imported, definition="All non-deleted leads in the workspace", window="all time"),
            "qualified_leads": metric(qualified, definition="Leads whose latest ICP class is strong or possible", window="all time"),
            "leads_approved_for_outreach": metric(approved_leads, definition="Distinct leads with at least one approved or sent message", window="all time"),
            "messages_sent_real": metric(sent_real, definition="Outbound messages accepted by a real provider (excludes simulated and manual)", window=win),
            "messages_sent_simulated": metric(sent_sim, definition="Outbound messages from the mock sandbox. Not real sends", window=win),
            "messages_sent_manual": metric(sent_manual, definition="LinkedIn/Instagram messages a person marked as sent", window=win),
            "leads_contacted": metric(contacted, definition="Distinct leads with at least one sent outbound message", window=win),
            "reply_rate": metric(None, replied, contacted, "Unique leads that replied / unique leads contacted", win),
            "positive_reply_rate": metric(None, positive, contacted, "Unique leads with a positive reply / unique leads contacted", win),
            "meeting_conversion": metric(None, meetings, contacted, "Opportunities at meeting stage or later / unique leads contacted", "all time"),
            "opportunities": metric(opps, definition="Opportunity records", window="all time"),
            "conversions": metric(won, definition="Opportunities in stage won", window="all time"),
            "unsubscribes": metric(unsub, definition="Leads with status unsubscribed", window="all time"),
            "bounces": metric(bounced, definition="Leads with status bounced", window="all time"),
        },
        "funnel": [
            {"stage": "Imported", "count": imported}, {"stage": "Qualified", "count": qualified},
            {"stage": "Approved", "count": approved_leads}, {"stage": "Contacted", "count": contacted},
            {"stage": "Replied", "count": replied}, {"stage": "Positive", "count": positive},
            {"stage": "Opportunity", "count": opps}, {"stage": "Won", "count": won}],
        "icp_distribution": _icp_dist(db, ws),
    }


def _icp_dist(db: Session, ws: uuid.UUID) -> list[dict]:
    col = func.coalesce(Lead.icp_class, "not scored")
    rows = db.execute(select(col, func.count()).where(Lead.workspace_id == ws, Lead.deleted_at.is_(None)).group_by(col)).all()
    order = ["strong", "possible", "weak", "unqualified", "insufficient", "not scored"]
    d = {k: v for k, v in rows}
    return [{"class": k, "count": d.get(k, 0)} for k in order]


def per_campaign(db: Session, ws: uuid.UUID) -> list[dict]:
    out = []
    for c in db.scalars(select(Campaign).where(Campaign.workspace_id == ws, Campaign.deleted_at.is_(None)).order_by(Campaign.created_at.desc())):
        o = overview(db, ws, c.id)["cards"]
        out.append({"id": str(c.id), "name": c.name, "status": c.status, "contacted": o["leads_contacted"]["value"],
                    "sent": o["messages_sent_real"]["value"] + o["messages_sent_simulated"]["value"] + o["messages_sent_manual"]["value"],
                    "reply_rate": o["reply_rate"], "positive_reply_rate": o["positive_reply_rate"]})
    return out


def per_channel(db: Session, ws: uuid.UUID) -> list[dict]:
    rows = db.execute(select(Message.channel, Message.simulated, Message.manual, func.count(), func.count(distinct(Message.lead_id)))
                      .where(Message.workspace_id == ws, Message.direction == "out", Message.state == "sent")
                      .group_by(Message.channel, Message.simulated, Message.manual)).all()
    return [{"channel": c, "kind": "simulated" if s else "manual" if m else "real", "messages": n, "leads": l} for c, s, m, n, l in rows]


def needs_attention(db: Session, ws: uuid.UUID) -> dict:
    failed_jobs = db.scalar(select(func.count()).select_from(Job).where(Job.workspace_id == ws, Job.state == "dead")) or 0
    failed_actions = db.scalar(select(func.count()).select_from(ScheduledAction).where(
        ScheduledAction.workspace_id == ws, ScheduledAction.state.in_(["failed", "needs_manual_check"]))) or 0
    from app.models import GeneratedMessage
    review = db.scalar(select(func.count()).select_from(GeneratedMessage).where(
        GeneratedMessage.workspace_id == ws, GeneratedMessage.status.in_(["draft", "needs_review"]))) or 0
    positive = db.scalar(select(func.count()).select_from(Message).where(
        Message.workspace_id == ws, Message.direction == "in", Message.intent.in_(list(POSITIVE)))) or 0
    upcoming = db.scalar(select(func.count()).select_from(ScheduledAction).where(
        ScheduledAction.workspace_id == ws, ScheduledAction.state == "pending")) or 0
    llm_fail = db.scalar(select(func.count()).select_from(AIUsageRecord).where(AIUsageRecord.workspace_id == ws, AIUsageRecord.ok.is_(False))) or 0
    mailbox_errors = sum(1 for a in db.scalars(select(ChannelAccount).where(ChannelAccount.workspace_id == ws, ChannelAccount.status == "active"))
                         if ((a.health or {}).get("imap") or {}).get("ok") is False)
    return {"mailbox_errors": mailbox_errors, "failed_jobs": failed_jobs, "failed_actions": failed_actions, "drafts_to_review": review,
            "positive_replies": positive, "upcoming_sends": upcoming, "llm_failures": llm_fail}


def timeseries(db: Session, ws: uuid.UUID, days: int = 30) -> list[dict]:
    """Per-day (UTC) counts of real+simulated+manual sends, replies and positive replies. Message-level counts."""
    days = max(1, min(days, 365))
    start = (datetime.now(timezone.utc) - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    when = func.date_trunc("day", func.coalesce(Message.sent_at, Message.created_at))
    rows = db.execute(select(when, Message.direction, Message.intent, func.count()).where(
        Message.workspace_id == ws, Message.state.in_(["sent", "received"]), func.coalesce(Message.sent_at, Message.created_at) >= start)
        .group_by(when, Message.direction, Message.intent)).all()
    out = {(start + timedelta(days=i)).date().isoformat(): {"date": (start + timedelta(days=i)).date().isoformat(), "sent": 0, "replies": 0, "positive": 0}
           for i in range(days)}
    for day, direction, intent, n in rows:
        d = out.get(day.date().isoformat())
        if d is None:
            continue
        if direction == "out":
            d["sent"] += n
        elif intent != "out_of_office":
            d["replies"] += n
            if intent in POSITIVE:
                d["positive"] += n
    return list(out.values())
