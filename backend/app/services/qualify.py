import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.scoring import Facts, evaluate
from app.domain.states import can_transition
from app.jobs import queue
from app.models import Campaign, CampaignLead, Company, Job, Lead
from app.services.audit import activity
from app.services.research import evidence_for

STATUS_FOR_CLASS = {"strong": "qualified", "possible": "qualified", "weak": "unqualified", "unqualified": "unqualified"}
EDITABLE = {"imported", "needs_research", "qualified", "unqualified"}


def qualify(db: Session, campaign: Campaign, lead: Lead, cl: CampaignLead | None = None) -> dict:
    ev = evidence_for(db, lead.workspace_id, lead.id)
    company = db.get(Company, lead.company_id) if lead.company_id else None
    text = " ".join([e.excerpt for e in ev] + [company.description or "" if company else "", lead.custom.get("description", "") if isinstance(lead.custom, dict) else ""])
    facts = Facts(industry=company.industry if company else None, region=lead.region, text=text.lower(),
                  evidence_count=len([e for e in ev if e.kind == "verified" and e.confidence != "low"]))
    res = evaluate(campaign.icp or {}, facts, campaign.thresholds or {})
    bd = res.breakdown()
    for target in (lead, cl):
        if target is not None:
            target.icp_score, target.icp_class, target.icp_confidence, target.icp_breakdown = res.score, res.klass, res.confidence, bd
    new_status = STATUS_FOR_CLASS.get(res.klass)
    if new_status and lead.status in EDITABLE and lead.status != new_status and can_transition(lead.status, new_status):
        lead.status = new_status
    activity(db, lead.workspace_id, lead.id, "lead.qualified", campaign=str(campaign.id), score=res.score, klass=res.klass)
    return {"score": res.score, "class": res.klass, "confidence": res.confidence}


@queue.handler("qualify_campaign")
def run_qualify(db: Session, job: Job) -> None:
    camp = db.get(Campaign, uuid.UUID(job.payload["campaign_id"]))
    if camp is None or camp.workspace_id != job.workspace_id:
        return
    for cl in db.scalars(select(CampaignLead).where(CampaignLead.campaign_id == camp.id)):
        lead = db.get(Lead, cl.lead_id)
        if lead and lead.workspace_id == camp.workspace_id:
            qualify(db, camp, lead, cl)
    db.commit()
