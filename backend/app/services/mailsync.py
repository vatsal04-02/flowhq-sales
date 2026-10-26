"""Pull replies and bounces from a real mailbox over IMAP and feed them through the same ingestion path as every
other provider. Read-only; the cursor only advances after a message is fully processed and committed."""
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.channels.imap import ImapClient, ImapError
from app.core.config import get_settings
from app.core.crypto import decrypt
from app.domain import mailparse
from app.jobs import queue
from app.models import ChannelAccount, Job, ProviderEvent
from app.services import replies

log = logging.getLogger("mailsync")


def imap_config(acct: ChannelAccount) -> dict | None:
    if acct.provider != "smtp" or not acct.credentials_enc:
        return None
    cfg = json.loads(decrypt(acct.credentials_enc)).get("imap")
    return cfg if cfg and cfg.get("host") else None


def client_for(cfg: dict) -> ImapClient:
    return ImapClient(cfg["host"], int(cfg.get("port", 993)), cfg.get("username", ""), cfg.get("password", ""), cfg.get("security", "ssl"))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _set_health(acct: ChannelAccount, ok: bool, **extra) -> None:
    h = dict(acct.health or {})
    h["imap"] = {"ok": ok, "checked_at": _now().isoformat(), **extra}
    acct.health = h


def process_message(db: Session, acct: ChannelAccount, uid: int, validity: int | None, raw: bytes) -> str:
    """Returns what happened: reply | bounce | unmatched | own | duplicate | skipped."""
    if not raw:
        return "skipped"
    p = mailparse.parse(raw)
    ext = f"imap:{acct.id}:{p.message_id}" if p.message_id else f"imap:{acct.id}:{validity}:{uid}"
    if p.from_addr and p.from_addr == acct.from_email.lower():
        return "own"  # a copy of something we sent
    if p.bounce is not None:
        ok = replies.ingest_bounce(db, acct.workspace_id, provider="imap", external_id=ext, email=p.bounce.recipient,
                                   original_message_id=p.bounce.original_message_id, permanent=p.bounce.permanent)
        return "bounce" if ok else "duplicate"
    if not p.from_addr:
        return "skipped"
    before = db.scalar(select(ProviderEvent.id).where(ProviderEvent.provider == "imap", ProviderEvent.external_id == ext[:300]))
    if before:
        return "duplicate"
    m = replies.ingest_inbound(db, acct.workspace_id, provider="imap", external_id=ext, from_email=p.from_addr, subject=p.subject,
                               body=p.body, in_reply_to=p.in_reply_to, references=p.references, auto_submitted=p.is_auto)
    return "reply" if m is not None else "unmatched"


def sync_account(db: Session, acct: ChannelAccount, client: ImapClient | None = None) -> dict:
    s = get_settings()
    cfg = imap_config(acct)
    if cfg is None:
        return {"skipped": "no imap configured"}
    state = dict(acct.sync_state or {})
    stats = {"fetched": 0, "reply": 0, "bounce": 0, "unmatched": 0, "own": 0, "duplicate": 0, "skipped": 0}
    try:
        res = (client or client_for(cfg)).fetch_new(state.get("last_uid"), state.get("uidvalidity"), s.imap_lookback_days, s.imap_max_per_sync)
    except ImapError as exc:
        _set_health(acct, False, error=str(exc))
        acct.sync_state = {**state, "next_at": (_now() + timedelta(seconds=s.imap_poll_seconds)).isoformat()}
        db.commit()
        return {"error": str(exc)}
    if res.uidvalidity is not None and state.get("uidvalidity") not in (None, res.uidvalidity):
        state.pop("last_uid", None)  # mailbox was renumbered: dedupe falls back to Message-ID based external ids
    for uid, raw in res.messages:
        try:
            outcome = process_message(db, acct, uid, res.uidvalidity, raw)
        except Exception:  # noqa: BLE001 - one bad message must not wedge the mailbox
            db.rollback()
            log.exception("could not process imap message uid=%s", uid)
            outcome = "skipped"
            acct = db.get(ChannelAccount, acct.id)
        stats["fetched"] += 1
        stats[outcome] = stats.get(outcome, 0) + 1
        state.update(uidvalidity=res.uidvalidity, last_uid=uid)
        acct.sync_state = {**state}  # cursor advances only after this message is handled
        db.commit()
    if res.uidvalidity is not None:
        state["uidvalidity"] = res.uidvalidity
    if res.messages:
        state["last_uid"] = res.messages[-1][0]
    if res.highest_uid is not None and not res.more:  # first sync: skip history older than the lookback window for good
        state["last_uid"] = max(state.get("last_uid") or 0, res.highest_uid)
    elif state.get("last_uid") is None:
        state["last_uid"] = 0
    state["next_at"] = (_now() + timedelta(seconds=0 if res.more else s.imap_poll_seconds)).isoformat()
    acct.sync_state = state
    _set_health(acct, True, new=stats["fetched"], replies=stats["reply"], bounces=stats["bounce"], unmatched=stats["unmatched"])
    db.commit()
    return stats


@queue.handler("imap_sync")
def run_sync(db: Session, job: Job) -> None:
    acct = db.get(ChannelAccount, uuid.UUID(job.payload["account_id"]))
    if acct is None or acct.workspace_id != job.workspace_id or acct.status != "active":
        return
    sync_account(db, acct)


def enqueue_sync(db: Session, acct: ChannelAccount, force: bool = False) -> Job | None:
    """At most one pending/running sync per account."""
    busy = db.scalars(select(Job).where(Job.type == "imap_sync", Job.state.in_(["pending", "running"]),
                                        Job.payload["account_id"].astext == str(acct.id)).limit(1)).first()
    if busy:
        return None if not force else busy
    return queue.enqueue(db, "imap_sync", {"account_id": str(acct.id)}, acct.workspace_id, max_attempts=2)


def enqueue_due(db: Session) -> int:
    n = 0
    for acct in db.scalars(select(ChannelAccount).where(ChannelAccount.provider == "smtp", ChannelAccount.status == "active")):
        if imap_config(acct) is None:
            continue
        nxt = (acct.sync_state or {}).get("next_at")
        if nxt and datetime.fromisoformat(nxt) > _now():
            continue
        if enqueue_sync(db, acct):
            n += 1
    db.commit()
    return n
