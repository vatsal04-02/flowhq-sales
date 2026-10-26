import uuid

from sqlalchemy import and_, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.domain.normalize import domain_of_email, normalize_email, normalize_phone
from app.models import SuppressionRecord


class SuppressionRepo:
    def __init__(self, db: Session, workspace_id: uuid.UUID):
        self.db, self.ws = db, workspace_id

    def add(self, kind: str, value_norm: str, reason: str, source: str | None = None) -> None:
        """Idempotent. Existing record keeps its original reason."""
        self.db.execute(
            insert(SuppressionRecord)
            .values(workspace_id=self.ws, kind=kind, value_norm=value_norm, reason=reason,
                    source=source, id=uuid.uuid4())
            .on_conflict_do_nothing(index_elements=["workspace_id", "kind", "value_norm"])
        )

    def add_raw(self, kind: str, raw: str, reason: str, source: str | None = None) -> str | None:
        if kind == "email":
            v = normalize_email(raw)
        elif kind == "phone":
            v = normalize_phone(raw)
        else:
            v = raw.strip().lower().lstrip("@") or None
        if v is None:
            return None
        self.add(kind, v, reason, source)
        return v

    def list(self) -> list[SuppressionRecord]:
        return list(self.db.scalars(
            select(SuppressionRecord).where(SuppressionRecord.workspace_id == self.ws)
            .order_by(SuppressionRecord.created_at.desc())))

    def get(self, rec_id: uuid.UUID) -> SuppressionRecord | None:
        return self.db.scalars(select(SuppressionRecord).where(
            SuppressionRecord.workspace_id == self.ws, SuppressionRecord.id == rec_id)).first()

    def is_suppressed(self, email_norm: str | None, phone_e164: str | None = None) -> str | None:
        """Return the reason if suppressed (by email, email-domain, or phone), else None."""
        conds = []
        if email_norm:
            conds.append(("email", email_norm))
            d = domain_of_email(email_norm)
            if d:
                conds.append(("domain", d))
        if phone_e164:
            conds.append(("phone", phone_e164))
        if not conds:
            return None
        rec = self.db.scalars(select(SuppressionRecord).where(
            SuppressionRecord.workspace_id == self.ws,
            or_(*[and_(SuppressionRecord.kind == k, SuppressionRecord.value_norm == v)
                  for k, v in conds])).limit(1)).first()
        return f"{rec.kind}:{rec.reason}" if rec else None
