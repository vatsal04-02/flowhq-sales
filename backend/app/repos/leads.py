import base64
import uuid
from datetime import datetime

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.domain.dedup import Identity, match_keys
from app.models import Company, Lead


class LeadRepo:
    """All lead/company queries are filtered by workspace_id here and nowhere else."""

    def __init__(self, db: Session, workspace_id: uuid.UUID):
        self.db, self.ws = db, workspace_id

    def get(self, lead_id: uuid.UUID) -> Lead | None:
        return self.db.scalars(select(Lead).where(
            Lead.workspace_id == self.ws, Lead.id == lead_id, Lead.deleted_at.is_(None))).first()

    def find_duplicate(self, ident: Identity) -> tuple[Lead, str] | None:
        """One query across all identifiers; the highest-confidence matching field is reported."""
        keys = match_keys(ident)
        if not keys:
            return None
        found = list(self.db.scalars(select(Lead).where(
            Lead.workspace_id == self.ws, Lead.deleted_at.is_(None),
            or_(*[getattr(Lead, f) == v for f, v in keys])).limit(10)))
        for field, value in keys:  # keys are in confidence order
            for lead in found:
                if getattr(lead, field) == value:
                    return lead, field
        return None

    def find_company_by_domain(self, domain: str) -> Company | None:
        return self.db.scalars(select(Company).where(
            Company.workspace_id == self.ws, Company.domain == domain,
            Company.deleted_at.is_(None))).first()

    def same_domain_same_lastname(self, domain: str | None, last_name: str | None) -> Lead | None:
        """Suggestion-only signal (never auto-merged)."""
        if not domain or not last_name:
            return None
        return self.db.scalars(
            select(Lead).join(Company, Lead.company_id == Company.id).where(
                Lead.workspace_id == self.ws, Company.domain == domain,
                Lead.last_name.ilike(last_name), Lead.deleted_at.is_(None)).limit(1)).first()

    def list(self, *, q: str | None = None, status: str | None = None, region: str | None = None,
             batch_id: uuid.UUID | None = None, cursor: str | None = None, limit: int = 50):
        stmt = select(Lead).where(Lead.workspace_id == self.ws, Lead.deleted_at.is_(None))
        if status:
            stmt = stmt.where(Lead.status == status)
        if region:
            stmt = stmt.where(Lead.region == region.upper())
        if batch_id:
            stmt = stmt.where(Lead.import_batch_id == batch_id)
        if q:
            like = f"%{q.strip()}%"
            stmt = stmt.outerjoin(Company, Lead.company_id == Company.id).where(or_(
                Lead.email_norm.ilike(like), Lead.first_name.ilike(like),
                Lead.last_name.ilike(like), Company.name.ilike(like), Company.domain.ilike(like)))
        if cursor:
            ts, lid = decode_cursor(cursor)
            stmt = stmt.where(or_(Lead.created_at < ts, and_(Lead.created_at == ts, Lead.id < lid)))
        rows = list(self.db.scalars(
            stmt.order_by(Lead.created_at.desc(), Lead.id.desc()).limit(limit + 1)))
        nxt = encode_cursor(rows[limit - 1]) if len(rows) > limit else None
        return rows[:limit], nxt


def encode_cursor(lead: Lead) -> str:
    return base64.urlsafe_b64encode(f"{lead.created_at.isoformat()}|{lead.id}".encode()).decode()


def decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    ts, lid = base64.urlsafe_b64decode(cursor.encode()).decode().split("|")
    return datetime.fromisoformat(ts), uuid.UUID(lid)
