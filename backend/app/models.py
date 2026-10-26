import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _id() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def _ws() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), ForeignKey("workspace.id"), nullable=False, index=True)


class Timestamps:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Workspace(Base, Timestamps):
    __tablename__ = "workspace"
    id: Mapped[uuid.UUID] = _id()
    name: Mapped[str] = mapped_column(String(200))
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    kill_switch: Mapped[bool] = mapped_column(Boolean, default=False)


class User(Base, Timestamps):
    __tablename__ = "user_account"
    id: Mapped[uuid.UUID] = _id()
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Membership(Base, Timestamps):
    __tablename__ = "membership"
    __table_args__ = (UniqueConstraint("workspace_id", "user_id"),)
    id: Mapped[uuid.UUID] = _id()
    workspace_id: Mapped[uuid.UUID] = _ws()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user_account.id"), index=True)
    role: Mapped[str] = mapped_column(String(20), default="rep")  # owner | admin | rep


class Company(Base, Timestamps):
    __tablename__ = "company"
    __table_args__ = (
        Index("uq_company_ws_domain", "workspace_id", "domain", unique=True,
              postgresql_where=text("domain IS NOT NULL AND deleted_at IS NULL")),
    )
    id: Mapped[uuid.UUID] = _id()
    workspace_id: Mapped[uuid.UUID] = _ws()
    name: Mapped[str | None] = mapped_column(String(300))
    domain: Mapped[str | None] = mapped_column(String(253))
    website: Mapped[str | None] = mapped_column(String(500))
    location: Mapped[str | None] = mapped_column(String(300))
    industry: Mapped[str | None] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ImportBatch(Base, Timestamps):
    __tablename__ = "import_batch"
    id: Mapped[uuid.UUID] = _id()
    workspace_id: Mapped[uuid.UUID] = _ws()
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("user_account.id"))
    filename: Mapped[str] = mapped_column(String(300))
    file_sha256: Mapped[str] = mapped_column(String(64))
    file_bytes: Mapped[bytes] = mapped_column(LargeBinary)
    headers: Mapped[list[str]] = mapped_column(JSONB, default=list)
    mapping: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict)
    default_region: Mapped[str | None] = mapped_column(String(2))  # phone parsing, e.g. "IN"
    status: Mapped[str] = mapped_column(String(20), default="uploaded")
    # uploaded | mapped | queued | running | completed | failed
    total_rows: Mapped[int] = mapped_column(Integer, default=0)
    next_row: Mapped[int] = mapped_column(Integer, default=1)  # resume cursor (1-based data row)
    created_count: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0)
    invalid_count: Mapped[int] = mapped_column(Integer, default=0)
    suppressed_count: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)


class ImportRowError(Base, Timestamps):
    __tablename__ = "import_row_error"
    __table_args__ = (UniqueConstraint("batch_id", "row_number"),)
    id: Mapped[uuid.UUID] = _id()
    workspace_id: Mapped[uuid.UUID] = _ws()
    batch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("import_batch.id"), index=True)
    row_number: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(20))  # invalid | duplicate
    reason: Mapped[str] = mapped_column(String(500))
    existing_lead_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    raw: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class Lead(Base, Timestamps):
    __tablename__ = "lead"
    __table_args__ = (
        Index("uq_lead_ws_email", "workspace_id", "email_norm", unique=True,
              postgresql_where=text("email_norm IS NOT NULL AND deleted_at IS NULL")),
        Index("uq_lead_batch_row", "import_batch_id", "import_row", unique=True,
              postgresql_where=text("import_batch_id IS NOT NULL")),
        Index("ix_lead_ws_created", "workspace_id", "created_at", "id"),
        Index("ix_lead_ws_phone", "workspace_id", "phone_e164"),
        Index("ix_lead_ws_linkedin", "workspace_id", "linkedin_url"),
        Index("ix_lead_ws_instagram", "workspace_id", "instagram_url"),
    )
    id: Mapped[uuid.UUID] = _id()
    workspace_id: Mapped[uuid.UUID] = _ws()
    company_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("company.id"), index=True)
    import_batch_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("import_batch.id"))
    import_row: Mapped[int | None] = mapped_column(Integer)
    first_name: Mapped[str | None] = mapped_column(String(200))
    last_name: Mapped[str | None] = mapped_column(String(200))
    title: Mapped[str | None] = mapped_column(String(300))
    email: Mapped[str | None] = mapped_column(String(320))  # as supplied
    email_norm: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(100))
    phone_e164: Mapped[str | None] = mapped_column(String(20))
    linkedin_url: Mapped[str | None] = mapped_column(String(500))
    instagram_url: Mapped[str | None] = mapped_column(String(500))
    source_url: Mapped[str | None] = mapped_column(String(1000))
    collected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    region: Mapped[str | None] = mapped_column(String(2))  # ISO country, drives send policy
    lawful_basis: Mapped[str | None] = mapped_column(String(500))
    custom: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    raw: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)  # original CSV values
    status: Mapped[str] = mapped_column(String(30), default="imported", index=True)
    opted_out: Mapped[bool] = mapped_column(Boolean, default=False)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("user_account.id"))
    possible_duplicate_of: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SuppressionRecord(Base, Timestamps):
    """Keyed on normalized values, independent of lead rows, so it survives edits/re-imports."""
    __tablename__ = "suppression_record"
    __table_args__ = (UniqueConstraint("workspace_id", "kind", "value_norm"),)
    id: Mapped[uuid.UUID] = _id()
    workspace_id: Mapped[uuid.UUID] = _ws()
    kind: Mapped[str] = mapped_column(String(10))  # email | domain | phone
    value_norm: Mapped[str] = mapped_column(String(320))
    reason: Mapped[str] = mapped_column(String(200))  # opt_out | bounce | manual | complaint
    source: Mapped[str | None] = mapped_column(String(300))


class Job(Base, Timestamps):
    __tablename__ = "job"
    __table_args__ = (Index("ix_job_claim", "state", "run_after"),)
    id: Mapped[uuid.UUID] = _id()
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("workspace.id"), index=True)
    type: Mapped[str] = mapped_column(String(60))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    state: Mapped[str] = mapped_column(String(10), default="pending")
    # pending | running | done | dead
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5)
    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)


class ActivityLog(Base):
    __tablename__ = "activity_log"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    workspace_id: Mapped[uuid.UUID] = _ws()
    lead_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    kind: Mapped[str] = mapped_column(String(60))
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditLog(Base):
    """Append-only. Never updated or deleted by application code."""
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    action: Mapped[str] = mapped_column(String(80))
    target: Mapped[str | None] = mapped_column(String(200))
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
