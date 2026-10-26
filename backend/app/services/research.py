"""Website research: deterministic fetch + extraction. No LLM here (fast, cheap, no hallucination)."""
import hashlib
import logging
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin, urlparse

import httpx
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.adapters.fetch import safe_fetcher as sf
from app.core.config import get_settings
from app.domain.research_extract import SERVICE_PATH, build_findings
from app.domain.states import can_transition
from app.jobs import queue
from app.models import Company, Job, Lead, ResearchEvidence
from app.services.audit import activity

log = logging.getLogger("research")


def website_for(db: Session, lead: Lead) -> str | None:
    if not lead.company_id:
        return None
    c = db.get(Company, lead.company_id)
    if not c:
        return None
    return c.website or (f"https://{c.domain}" if c.domain else None)


def _pages_to_fetch(home_url: str, home: dict) -> list[str]:
    host = urlparse(home_url).hostname
    urls: list[str] = []
    for href, _text in home["links"]:
        if not href or href.startswith(("mailto:", "tel:", "#", "javascript:")):
            continue
        u = urljoin(home_url, href)
        pu = urlparse(u)
        if pu.hostname == host and SERVICE_PATH.search(pu.path) and u.split("#")[0] not in urls and u.rstrip("/") != home_url.rstrip("/"):
            urls.append(u.split("#")[0])
    return urls[: max(get_settings().research_max_pages - 1, 0)]


def research_lead(db: Session, lead: Lead, force: bool = False) -> str:
    s = get_settings()
    now = datetime.now(timezone.utc)
    if lead.opted_out or lead.status in ("suppressed", "unsubscribed", "bounced"):
        return "skipped"
    if (not force and lead.research_status in ("done", "insufficient") and lead.research_at
            and now - lead.research_at < timedelta(days=s.research_ttl_days)):
        return "cached"
    url = website_for(db, lead)
    if not url:
        lead.research_status, lead.research_at = "insufficient", now
        activity(db, lead.workspace_id, lead.id, "research.insufficient", reason="no website or company domain")
        return "insufficient"
    pages: list[dict] = []
    try:
        if not sf.robots_allows(url):
            lead.research_status, lead.research_at = "failed", now
            activity(db, lead.workspace_id, lead.id, "research.failed", reason="robots.txt disallows fetching")
            return "failed"
        final, html = sf.fetch_html(url)
        home = sf.extract(html)
        pages.append({"url": final, **home})
        for u in _pages_to_fetch(final, home):
            try:
                if sf.robots_allows(u):
                    fu, h = sf.fetch_html(u)
                    pages.append({"url": fu, **sf.extract(h)})
            except (sf.FetchBlocked, httpx.HTTPError):
                continue
    except sf.FetchBlocked as exc:
        lead.research_status, lead.research_at = "failed", now
        activity(db, lead.workspace_id, lead.id, "research.failed", reason=str(exc)[:200])
        return "failed"
    # httpx transport errors propagate -> the job is retried with backoff

    findings = build_findings(pages)
    db.execute(delete(ResearchEvidence).where(ResearchEvidence.lead_id == lead.id,
                                              ResearchEvidence.workspace_id == lead.workspace_id))
    for f in findings:
        db.add(ResearchEvidence(workspace_id=lead.workspace_id, lead_id=lead.id, url=f["url"], finding=f["finding"],
                                excerpt=f["excerpt"], kind=f["kind"], confidence=f["confidence"], retrieved_at=now,
                                content_hash=hashlib.sha256(f["excerpt"].encode()).hexdigest()))
    meaningful = [f for f in findings if f["topic"] != "sample"]
    lead.research_status = "done" if meaningful else "insufficient"
    lead.research_at = now
    if lead.status == "imported" and can_transition("imported", "needs_research"):
        lead.status = "needs_research"
    activity(db, lead.workspace_id, lead.id, f"research.{lead.research_status}", pages=len(pages), evidence=len(findings))
    return lead.research_status


@queue.handler("research_lead")
def run_research(db: Session, job: Job) -> None:
    lead = db.get(Lead, uuid.UUID(job.payload["lead_id"]))
    if lead is None or lead.workspace_id != job.workspace_id:
        return
    research_lead(db, lead, force=bool(job.payload.get("force")))
    db.commit()


def enqueue_research(db: Session, workspace_id: uuid.UUID, lead_ids: list[uuid.UUID], force: bool = False) -> int:
    for lid in lead_ids:
        queue.enqueue(db, "research_lead", {"lead_id": str(lid), "force": force}, workspace_id, max_attempts=3)
    return len(lead_ids)


def evidence_for(db: Session, workspace_id: uuid.UUID, lead_id: uuid.UUID) -> list[ResearchEvidence]:
    return list(db.scalars(select(ResearchEvidence).where(
        ResearchEvidence.workspace_id == workspace_id, ResearchEvidence.lead_id == lead_id)
        .order_by(ResearchEvidence.created_at)))
